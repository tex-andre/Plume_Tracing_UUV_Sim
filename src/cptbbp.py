#!/usr/bin/env python

# written by: ETHAN PARK

# Chemical Plume Tracing - Behaviour Based Planning Algorithm

# Algorithm based on: 
# "Chemical Plume Tracing via an Autonomous Underwater Vehicle" by 
# Jay A. Farrell, Shuo Pang, and Wei Li

import rospy
import numpy as np

from std_msgs.msg import Header
from uuv_control_msgs.srv import GoTo
from uuv_control_msgs.msg import Waypoint
from uuv_sensor_ros_plugins_msgs.msg import ChemicalParticleConcentration
from geometry_msgs.msg import Point, Vector3, Twist, TwistWithCovariance
from nav_msgs.msg import Odometry

THRESHOLD = 0.005 					#particle concentration threshold for detecting plume
CURRENT_FLOW = np.array([1.0, 0.0]) # [x,y] vector of the current flow
BETA_OFFSET = 20 					#angle offset relative to upflow
UPFLOW = np.array([-1.0, 0.0]) 		#180 rotation of CURRENT_FLOW
LAMBDA = 500000000 					#plume detection time threshold (0.5 seconds)

alg_state = 0                   #global var for which state the algorithm is currently in
								#0 for init, 1 for find, 2 for track-in, 3 for track-out, 4 for reacquire, 5 (maybe) for source declared
particle_concentration = 0.0    #global var for particle concentration
auv_location = None             #global var for robot position
auv_heading = None              #global var for robot heading vector
lhs = 0                     	#global var for which side of plume robot will drive out of
t_last = 0                  	#global var for last time at which plume was detected
lost_pnts = []          		#last detection points stored when track out is triggered
ldp = None                     	#global var for last detection point

#Calculate angle between two vectors (counter-clockwise positive)
def angle_between(v1,v2):
	rad1 = np.arctan2(v1[1],v1[0]) #arctan2 args are y,x (weird)
	rad2 = np.arctan2(v2[1],v2[0])
	return np.rad2deg(rad2-rad1)

#Track In behavior of algorithm
def track_in(gotoservice,interpolator):
	global lhs, t_last, ldp

	if(particle_concentration >= THRESHOLD): #stay in track-in
		alg_state = 2
		#calculate lhs var using angle between upflow and auv_heading
		ang = angle_between(UPFLOW,auv_heading)
		if(ang > 0): #heading is counter-clockwise from upflow
			lhs = 1
		else:
			lhs = -1

		#update t_last
		now = rospy.get_rostime()
		t_last = now.nsecs

		#update last detection point
		ldp = auv_location

		#calculate heading and new waypoint
		offsetrad = lhs*np.deg2rad(BETA_OFFSET)
		rotmatrix = np.array([[np.cos(offsetrad), -np.sin(offsetrad)],[np.sin(offsetrad), np.cos(offsetrad)]])
		new_heading = np.dot(UPFLOW,rotmatrix) #2D heading
		new_heading = new_heading/np.linalg.norm(new_heading)
		print("Calculated heading: " + str(new_heading[0]) + "," + str(new_heading[1]))
		threed_heading = np.array([new_heading[0],new_heading[1],0.0])
		new_waypoint = np.add(threed_heading,auv_location)
		
		#create waypoint message
		wp = Waypoint()
		wp.header.stamp = rospy.Time.now()
		wp.header.frame_id = "world"
		wp.point.x = new_waypoint[0]
		wp.point.y = new_waypoint[1]
		wp.point.z = new_waypoint[2]
		wp.max_forward_speed = 0.4
		wp.heading_offset = 0.0
		wp.use_fixed_heading = False

		#rosservice call to Go_To
		try:
			res = gotoservice(wp,wp.max_forward_speed,str(interpolator))
			print("Go To service call successful: " + str(res))
		except rospy.ServiceException, e:
			print("Service call failed: %s"%e)

	elif(rospy.get_rostime().nsecs - t_last > LAMBDA): #go to track-out
		lost_pnts.append(ldp)
		alg_state = 3

#callback function for particle concentration subscriber
def readconcentration(msg):
	global particle_concentration, auv_location
	particle_concentration = msg.concentration
	auv_location = np.array([msg.position.x, msg.position.y, msg.position.z])


#callback function for auv pose subscriber
def readauvpose(msg):
	global auv_heading
	auv_heading = np.array([msg.twist.twist.linear.x, msg.twist.twist.linear.y])


if __name__=='__main__':
	rospy.init_node('CPT_BBP')

	part_conc_sub = rospy.Subscriber(
		'rexrov2/particle_concentration', 
		ChemicalParticleConcentration, 
		readconcentration)

	auvpos_sub = rospy.Subscriber(
		'rexrov2/pose_gt',
		Odometry,
		readauvpose)

	interpolator = rospy.get_param('~interpolator', 'lipb')
	
	try:
		rospy.wait_for_service('rexrov2/go_to', timeout=15)
	except rospy.ROSException:
		raise rospy.ROSException('Service not available!')
	
	try:
		goto = rospy.ServiceProxy('rexrov2/go_to', GoTo)
	except rospy.ROSException as e:
		raise rospy.ROSException('Service proxy failed, error=%s', str(e))

	while not rospy.is_shutdown():
		#running the algorithm to quickly makes for some... interesting AUV behavior
		r = rospy.Rate(1)
		r.sleep()
		if(particle_concentration > 0):
			print("Particle concentration = " + str(particle_concentration))
		print("AUV heading: " + str(auv_heading[0]) + "," + str(auv_heading[1]))
		#check algorithm state and run appropriate behavior
		#for now, checking track-in behavior
		track_in(goto,interpolator)

	# iwp = Waypoint()
	# iwp.header.stamp = rospy.Time.now()
	# iwp.header.frame_id = "world"
	# iwp.point.x = 5
	# iwp.point.y = 0
	# iwp.point.z = -24
	# iwp.max_forward_speed = 0.4
	# iwp.heading_offset = 0.0
	# iwp.use_fixed_heading = False

	# res = goto(iwp,iwp.max_forward_speed, str(interpolator))
	# print("Initial Go To service call successful: " + str(res))