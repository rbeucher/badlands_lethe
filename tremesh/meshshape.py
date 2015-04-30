import numpy as np
import shapely.geometry, triangle
from time import clock
from polysimplify import VWSimplifier

def read_poly(file_name):
	"""
	Simple poly-file reader, that creates a python dictionary 
	with information about vertices, edges and holes.
	It assumes that vertices have no attributes or boundary markers.
	It assumes that edges have no boundary markers.
	No regional attributes or area constraints are parsed.
	"""

	output = dict()
	
	# open file and store lines in a list
	polyfile = open(file_name, 'r')
	lines = polyfile.readlines()
	polyfile.close()
	lines = [x.strip('\n').split() for x in lines]
	
	# Store vertices
	vertices= []
	N_vertices, dimension, attr, bdry_markers = [int(x) for x in lines[0]]
	# We assume attr = bdrt_markers = 0
	for k in range(N_vertices):
		label, x, y = [items for items in lines[k+1]]
		vertices.append([float(x), float(y)])
	if len(vertices) > 0:
		output['vertices']=np.array(vertices)

	# Store segments
	segments = []
	N_segments, bdry_markers = [int(x) for x in lines[N_vertices+1]]
	for k in range(N_segments):
		label, pointer_1, pointer_2 = [items for items in lines[N_vertices+k+2]]
		segments.append([int(pointer_1)-1, int(pointer_2)-1])
	if len(segments) > 0:
		output['segments'] = np.array(segments)

	# Store holes
	N_holes = int(lines[N_segments+N_vertices+2][0])
	holes = []
	for k in range(N_holes):
		label, x, y = [items for items in lines[N_segments + N_vertices + 3 + k]]
		holes.append([float(x), float(y)])
	if len(holes) > 0:
		output['holes'] = np.array(holes)
	
	return output


def point_in_poly(x,y,poly):
	"""
	Tests whether a point is inside a polygon using a ray-casting method
	Will return True if the point is on the edge of a polygon or a vertex
	Polygons are defined as a list of (x,y) tuples.
	<http://geospatialpython.com/2011/08/point-in-polygon-2-on-line.html>
	"""
	# check if point is a vertex
	if (x,y) in poly:
		return True

	# check if point is on a boundary
	for i in range(len(poly)):
		p1 = None
		p2 = None
		if i==0:
			p1 = poly[0]
			p2 = poly[1]
		else:
			p1 = poly[i-1]
			p2 = poly[i]
		if p1[1] == p2[1] and p1[1] == y and x > min(p1[0], p2[0]) and x < max(p1[0], p2[0]):
			return True

	n = len(poly)
	inside = False

	p1x,p1y = poly[0]
	for i in range(n+1):
		p2x,p2y = poly[i % n]
		if y > min(p1y,p2y):
			if y <= max(p1y,p2y):
				if x <= max(p1x,p2x):
					if p1y != p2y:
						xints = (y-p1y)*(p2x-p1x)/(p2y-p1y)+p1x
				if p1x == p2x or x <= xints:
					inside = not inside
		p1x,p1y = p2x,p2y

	if inside:
		return True
	else:
		return False


class Shape2Mesh:
	"""
	Create an unstructured triangular mesh from complex shapes.
	- Uses the shapely and triangle python modules.

	Add any number of shapes - this class tries to preserve their topology
	while generating a quality mesh.
	The shapes, and therefore mesh, will be simplified by a given ratio.
	"""
	def __init__(self, samples, verbose=True):
		"""
		Initialise a blank space and specify a maximum number of samples to use.
		Shapes are added to these data structures later on.
		"""
		self.shapelist = []
		self.samples = samples
		self.verbose = verbose
		self.shape = Shape2Mesh.shape() # initialise shape subclass
				
		return

	class shape:
		""" Class to handle all shape instances """
		def __init__(self):
			shapelist = dict()
			shapelist['poly'] = []
			shapelist['line'] = []
			shapelist['point'] = []
			self.shapelist = shapelist
			return

	def createPolygon(self, vertices):
		return shapely.geometry.Polygon(vertices)
	def createLine(self, vertices):
		return shapely.geometry.LineString(vertices)
	def createPoint(self, vertices):
		return shapely.geometry.Point(vertices)

	def newShape(self, name, vertices, shapetype='polygon'):
		"""
		Create a new shape from a list of vertices
		Vertices need to be ordered to preserve concavities
		shapetype can be either 'polygon', 'line', or 'point'
		Shapes are stored as self.shape.name
		"""
		name = str(name) #ensure string
		self.shapelist.append(name)

		if shapetype in ['poly', 'polygon']:
			self.shape.shapelist['poly'].append(name)
			setattr(self.shape, name, self.createPolygon(vertices))
		elif shapetype == 'line':
			self.shape.shapelist['line'].append(name)
			setattr(self.shape, name, self.createLine(vertices))
		elif shapetype == 'point':
			self.shape.shapelist['point'].append(name)
			setattr(self.shape, name, self.createPoint(vertices))
		else:
			raise Exception("shapetype must be 'polygon', 'line', or 'point'")

		if self.verbose:
			print " - %s '%s' created with %i vertices" % (shapetype.upper(), name, len(vertices))

		return

	def dedup(self, seq):
		"""
		Remove duplicate entries in a list while maintaining order.
		Important to avoid any issues with Delaunay triangulation.
		"""
		seen = set()
		seen_add = seen.add
		return [ x for x in seq if not (x in seen or seen_add(x))]

	def intersect(self, xy, shapeName):
		"""
		Returns 'True' or 'False' if point intersects a polygon
		"""
		pt = shapely.geometry.Point(xy)
		intersect = getattr(self.shape, shapeName).intersects(pt)
		return intersect


	def resolution(self):
		""" Calculate resolution from total area """
		area = 0.0
		for s in self.shapelist:
			area += getattr(self.shape, s).area
		
		resolution = area**0.5 / self.samples

		self.area = area
		self.resolution = resolution

		if self.verbose:
			print " - Total mesh area of %.2f and resolution %.2f" % (area, resolution)

		return resolution

	def simplify(self, tolerance, shapeName=''):
		"""
		Manually simplify shapes while preserving topology within a certain topology.
		Default action is to simplify all shapes with a given tolerance,
		but a single shape can also be specified.
		"""
		if shapeName == '':
			for s in self.shapelist:
				setattr(self.shape, s, getattr(self.shape, s).simplify(tolerance))
		else:
			shapeName = str(shapeName) #ensure string
			setattr(self.shape, shapeName, getattr(self.shape, shapeName).simplify(tolerance))


	def boundary_mask(self, tri):
		""" Create boundary mask from hull """

		bmask = np.zeros(len(self.x), dtype=bool)
		vertices = zip(self.x, self.y) # Convert back to tuples

		if self.is_concave:
			# Haven't worked this out yet!
			pass
		else:
			# triangle has a convex hull routine
			hull = triangle.convex_hull(tri['vertices'])
			convex_hull = zip( hull[:,0], hull[:,1] )
			for i, vert in enumerate(vertices):
				if vert in convex_hull:
					bmask[i] = True

		return bmask

	def meshit(self, importPoly='', is_concave=False):
		"""
		Create the Delaunay triangulation from previously defined shapes
		If you want to preserve concave structures, set is_concave=True
		Separate .poly file can be easily imported and triangulated.
		"""
		t = clock()

		# resolution = self.resolution() # For some reason this returns a TypeError
		self.is_concave = is_concave

		if importPoly != '':
			D = read_poly(importPoly)

		else:
			D = dict()

			# self.simplify(1000, s) # Adjust resolution

			# Create vertices from shapes
			vertices = []
			for s in self.shapelist:
				# Extract vertices
				try:
					getattr(self.shape, s).exterior.coords
				except AttributeError:
					# Must be a line or point
					sxsy = list( getattr(self.shape, s).coords )
				else:
					sxsy = list( getattr(self.shape, s).exterior.coords )
				vertices.extend(sxsy)
			vertices = self.dedup(vertices)

			D['vertices'] = np.array(vertices)

			# Create segments from shapes
			# Only necessary if concave
			if is_concave:
				hull = self.createPolygon(ver)
				hxhy = list(hull.exterior.coords)
				hxhy = self.dedup(hxhy)
				segments = zip( np.arange(0,len(hxhy),dtype=int), np.append(np.arange(1,len(hxhy),dtype=int), 0) )

				D['segments'] = np.array(segments)

		# Store original dictionary for further refinement
		self.meshDict = D

		# triangulate
		args = 'q20'
		if is_concave:
			args += 'p'
			tri = triangle.triangulate(D, args)
		else:
			tri = triangle.triangulate(D, args)


		if self.verbose:
			print " - Mesh triangulation complete.\n   %i vertices in %f secs with arguments '%s'" % (len(tri['vertices']), clock()-t, args)

		self.x = tri['vertices'][:,0]
		self.y = tri['vertices'][:,1]
		self.simplicies = tri['triangles']
		self.centroids = (tri['vertices'][tri['triangles'][:,0]] + tri['vertices'][tri['triangles'][:,1]] + tri['vertices'][tri['triangles'][:,2]])/3
		self.bmask = self.boundary_mask(tri)

		# self.tri = tri # REMOVE

		return


	def refineMesh(self, args):
		"""
		See the API <http://dzhelil.info/triangle> for information on optional arguments.
		Common arguments (use any combination):
			p - triangulates a Planar Straight Line Graph.
			a - imposes a maximum area for each triangle.
			q - quality mesh generation no angles smaller than specified degrees (default: 20).
			c - encloses convex hull with line segments
		"""
		t = clock()
		args = str(args) #ensure string
		tri = triangle.triangulate(self.meshDict, args)

		self.x = tri['vertices'][:,0]
		self.y = tri['vertices'][:,1]
		self.simplicies = tri['triangles']
		self.centroids = (tri['vertices'][tri['triangles'][:,0]] + tri['vertices'][tri['triangles'][:,1]] + tri['vertices'][tri['triangles'][:,2]])/3
		self.bmask = self.boundary_mask(tri)

		if self.verbose:
			print " - Mesh refinement complete.\n   %i vertices in %f secs with arguments '%s'" % (len(tri['vertices']), clock()-t, args)

		return


	def shapeMap(self):
		"""
		Returns a list of integers corresponding to each shape
		"""
		# vertices = zip(self.tri['vertices'][:,0], self.tri['vertices'][:,1]) # Convert back to tuples
		centroids = zip( self.centroids[:,0],self.centroids[:,1] ) # Convert back to tuples

		shapeMap = np.zeros(len(centroids), dtype=int)
		# Remove vertices as they are added to the map
		for i, s in enumerate(self.shapelist):
			for j, vert in enumerate(centroids):
				if self.intersect(vert, s):
					shapeMap[j] = i
					# some vertices will intersect other shapes
					# but what can you do!?

		return shapeMap


	def plot(self, filename=''):
		"""
		Plot mesh coloured by shape.
		Option to save the figure to directory.
		"""
		import matplotlib.pyplot as plt
		from matplotlib.pylab import cm

		fig = plt.figure(1)
		ax = fig.add_subplot(111, xlim=[np.min(self.x), np.max(self.x)], ylim=[np.min(self.y), np.max(self.y)])
		
		tc = ax.tripcolor(self.x, self.y, self.simplicies, facecolors=self.shapeMap(), edgecolors='k', cmap=cm.terrain, shading='flat', alpha=0.5)
		tc.set_clim(0, len(self.shapelist)+0.5)
		ax.scatter(self.x, self.y, c='k')
		fig.colorbar(tc)

		if filename == '':
			plt.show()
		else:
			# assert type(filename) is str, "filename is not a string"
			acceptable_formats = ['.png', '.jpg', 'jpeg', '.pdf', '.gif', '.eps', '.fig']
			assert filename[-4:] in acceptable_formats, "filename is not supported\nChoose between .png, .jpg, .pdf, .eps, etc."
			plt.savefig(filename, bbox_inches='tight')
