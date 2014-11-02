import theano
import theano.tensor as T
import numpy         as np
from theano.printing import Print
from theano_toolkit import utils as U
from theano_toolkit.parameters import Parameters
from theano_toolkit import hinton
import controller
import scipy

def cosine_sim(k,M):
	k_unit = k / T.sqrt(T.sum(k**2))
	k_unit = T.patternbroadcast(k_unit.reshape((1,k_unit.shape[0])),(True,False))
	k_unit.name = "k_unit"
	M_lengths = T.patternbroadcast(T.sqrt(T.sum(M**2,axis=1)).reshape((M.shape[0],1)),(False,True))
	M_unit = M / M_lengths
	M_unit.name = "M_unit"
#	M_unit = Print("M_unit")(M_unit)
	return T.sum(k_unit * M_unit,axis=1)

def build_step(P,controller,mem_size,mem_width,similarity=cosine_sim):
	circ_convolve = scipy.linalg.circulant(np.arange(mem_size)).T
	P.memory_init = 0.1 * np.random.randn(mem_size,mem_width)
	memory_init   = P.memory_init
	P.read_weight_init = np.ones((mem_size,))
	P.add_weight_init = np.ones((mem_size,))
	P.erase_weight_init = np.ones((mem_size,))
	read_weight_init  = U.vector_softmax(P.read_weight_init)
	erase_weight_init = U.vector_softmax(P.erase_weight_init)
	add_weight_init   = U.vector_softmax(P.add_weight_init)
	def build_memory_curr(M_prev,erase_head,erase_weight,add_head,add_weight):
		erase_weight = T.patternbroadcast(erase_weight.reshape((erase_weight.shape[0],1)),(False,True))
		add_weight   = T.patternbroadcast(add_weight.reshape((add_weight.shape[0],1)),(False,True))

		erase_head = T.patternbroadcast(erase_head.reshape((1,erase_head.shape[0])),  (True,False))
		add_head   = T.patternbroadcast(add_head.reshape((1,add_head.shape[0])),      (True,False))

		M_erased = M_prev   * (erase_weight * (1 - erase_head))
		M_curr   = M_erased + (add_weight   * add_head)
		return M_curr
	
	def build_read(M_curr,weight_curr):
		return T.dot(weight_curr, M_curr)

	def build_weight_curr(weight_prev,M_curr,head):
		"""
		This function is best described by Figure 2 in the paper.
		"""
		# 3.3.1 Focusing b Content
		weight_c = U.vector_softmax(head.beta * similarity(head.key,M_curr))

		# 3.3.2 Focusing by Location
		weight_g = head.g * weight_c + (1 - head.g) * weight_prev
		weight_shifted = T.dot(weight_g,head.shift[circ_convolve])
		weight_sharp   = weight_shifted ** head.gamma
		weight_curr    = weight_sharp / T.sum(weight_sharp)

		return weight_curr
	
	def step(input_curr,M_prev,
			read_weight_prev,
			erase_weight_prev,
			add_weight_prev):
		#print read_prev.type
		
		read_prev = build_read(M_prev,read_weight_prev)
		output,[read,erase,add] = controller(input_curr,read_prev)

		read_weight  = build_weight_curr(read_weight_prev, M_prev,read)
		erase_weight = build_weight_curr(erase_weight_prev,M_prev,erase)
		add_weight   = build_weight_curr(add_weight_prev,  M_prev,add)
		
		M_curr = build_memory_curr(M_prev,erase.head,erase_weight,add.head,add_weight)
		#print [i.type for i in [erase_curr,add_curr,key_curr,shift_curr,beta_curr,gamma_curr,g_curr,output]]
		#print weight_curr.type
		return M_curr,read_weight,erase_weight,add_weight,output
	return step,[memory_init,read_weight_init,erase_weight_init,add_weight_init,None]

def build(P,mem_size,mem_width,input_size,ctrl):
	output_size = input_size
	step,outputs_info = build_step(P,ctrl,mem_size,mem_width)
	def predict(input_sequence):
		outputs,_ = theano.scan(
				step,
				sequences    = [input_sequence],
				outputs_info = outputs_info
			)
		return outputs[-1]
	
	return predict

