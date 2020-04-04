from myhdl import *

from .. import general
from ..general import test_resize as t
from .cosim_common import *

from myhdl import ConversionError
from myhdl.conversion import yshelper

@block
def wrapper(uut, clk, ce, reset, mode, data_in, data_out, **kwargs):
	"Black box for arbitrary tests with a data in and a data out port"

	imm = kwargs['IMM']

	a = uut(clk, mode, data_out, data_in, imm)

	return instances()



@block
def tb_unit(uut, syn, async_reset, DATA_IN, DATA_IMM, MODE, DATA_OUT):
	mode = Signal(t.t_lmode.LW)
	clk = Signal(bool())
	debug, debug_syn = [ Signal(bool(0)) for i in range(2) ]
	ce = Signal(bool())
	reset = ResetSignal(0, 1, isasync = async_reset)

	data_in = Signal(modbv()[DATA_IN[1]:])
	data_out, data_out_syn = [ Signal(modbv()[DATA_OUT[1]:]) for i in range(2) ]
	data_check = Signal(modbv()[DATA_OUT[1]:])

	inst_clkgen = clkgen(clk, 20)

	imm = DATA_IMM

	inst_uut =      uut(clk, mode, data_out, data_in, imm)
	# Synthesized result unit to co-simulate against:
	inst_syn = syn(uut, clk, ce, reset, mode, data_out_syn, data_in)

	@instance
	def stimulus():
		data_in.next = DATA_IN[0]
		data_check.next = DATA_OUT[0]
		mode.next = MODE
		clk.next = 0

		yield delay(10)
		clk.next = not clk
		yield delay(10)
		clk.next = not clk
		yield delay(10)
		clk.next = not clk
		yield delay(10)
		clk.next = not clk

		if data_out == data_check and data_out_syn == data_check:
			print("PASS")
		else:
			print("\n\n\n")
			print("===========  FAILURE REPORT ============")
			print("Expected output: %x" % data_check)
			print("Output from simulation: %x" % data_out)
			print("Output from synthesis: %x" % data_out_syn)
			print("========================================")
			raise ValueError("Mismatch: sim: %x, syn: %x" %(data_out, data_out_syn))

	return instances()

# @block
# def tb_resize_vectors(uut, DATA_IN, DATA_IMM, MODE, DATA_OUT):
# 	data_in = Signal(modbv()[DATA_IN[1]:])
# 	data_out, data_check = [ Signal(modbv()[DATA_OUT[1]:]) for i in range(2) ]
# 	mode = Signal(t_lmode.LW)
# 	clk = Signal(bool(0))
# 
# 	if (type(DATA_IMM) == type(1)) or DATA_IMM == None:
# 		inst_uut = uut(clk, mode, data_out, data_in, DATA_IMM)
# 	else:
# 		sig = Signal(DATA_IMM)
# 
# 		inst_uut = uut(clk, mode, data_out, data_in, sig)
# 
# 
# 	@instance
# 	def stimulus():
# 		data_in.next = DATA_IN[0]
# 		data_check.next = DATA_OUT[0]
# 		mode.next = MODE
# 		clk.next = 0
# 
# 		yield delay(10)
# 		clk.next = not clk
# 		yield delay(10)
# 		clk.next = not clk
# 
# 		if data_out != data_check:
# 			raise ValueError("resize error, result %x" % data_out)
# 
# 	return instances()

def run_test(tb, cycles = 2000):
	tb.config_sim(backend = 'myhdl', timescale="1ps", trace=True)
	tb.run_sim(cycles)
	tb.quit_sim() # Quit so we can run another one
	return True

def check_resize_vectors(succeed, uut, din, imm, m, dout):
	arst = False
	syn = mapped_wrapper
	if not succeed: # expected to throw error:
		try:
			# run_test(tb_resize_vectors(uut, din, imm, m, dout))
			run_test(tb_unit(uut, syn, arst, din, imm, m, dout))
		except ConversionError:
			pass
		except ValueError:
			pass
	else:
		assert run_test(tb_unit(uut, syn, arst, din, imm, m, dout))
		# assert run_test(tb_resize_vectors(uut, din, imm, m, dout))


t_lmode = t.t_lmode

@block
def resize_vectors(clk, mode, data_out, data_in, imm):
	"Resize signed and unsigned test case"
	@always(clk.posedge)
	def worker():
		if mode == t_lmode.LBU:
			data_out.next = data_in[8:]
		elif mode == t_lmode.LHU:
			data_out.next = data_in[16:]
		elif mode == t_lmode.LB:
			data_out.next = data_in[8:].signed()
		elif mode == t_lmode.LH:
			data_out.next = data_in[16:].signed()
		else:
			data_out.next = data_in

	return instances()

@block
def resize_vectors_op_sane(clk, mode, data_out, data_in, IMM):
	"""Sane way to avoid warnings during VHDL conversion
It is mandatory to define this as constant first, if written verbosely
in the statements below, invalid VHDL will be generated.
"""
	const_imm8 = IMM & 0xff
	const_imm16 = IMM & 0xffff

	@always_comb
	def worker():
		if mode == t_lmode.LB:
			data_out.next = data_in[8:].signed() | const_imm8
		elif mode == t_lmode.LH:
			data_out.next = data_in[16:].signed() | const_imm16
		elif mode == t_lmode.LBU:
			data_out.next = data_in[8:] | const_imm8
		elif mode == t_lmode.LHU:
			data_out.next = data_in[16:] | const_imm16
		else:
			data_out.next = data_in | IMM


	return instances()


RV = resize_vectors
RVS = resize_vectors_op_sane
RVA = t.resize_vectors_add
RVO = t.resize_vectors_op
	
CHECK_LIST0 = (
	( True,  RV,  (0x80, 32),       None,            t_lmode.LB,  (0xffffff80, 32) ),
	( True,  RV,  (0x80, 32),       None,            t_lmode.LBU, (0x00000080, 32) ),
	( True,  RV,  (0xbeef, 32),     None,            t_lmode.LH,  (0xffffbeef, 32) ),
	( True,  RV,  (0xbeef, 32),     None,            t_lmode.LHU, (0x0000beef, 32) ),
	( True,  RV,  (0x8000beef, 32), None,            t_lmode.LW,  (0x8000beef, 32) ),
	( True,  RVA, (0x80, 24),       intbv(-32)[24:], t_lmode.LW,  (0xffffc1, 24) ),
	( True,  RVA, (4, 4),   intbv(4)[4:],            t_lmode.LW,  (9, 4) ),

	( False, RVO, (0x80, 16),       0x0f0000,        t_lmode.LW,  (0x0f0080, 24) ),
)

# Test cases that are not expected to be sane
CHECK_LIST1 = (
	# Failing due to lack of proper variable support
	( True,  RVS, (0x80, 32),       0x0f0000,        t_lmode.LW,  (0x000080, 16) ),
	# Adder:
	# Make sure things don't go wrong at the bounds:

)

def test_resize_vectors_ok():
	for succeed, uut, din, imm, m, dout in CHECK_LIST0:
		run_conversion(uut, False, wrapper, IMM = imm, MODE = m, DATA_IN = din, DATA_OUT = dout)
		check_resize_vectors(succeed, uut, din, imm, m, dout)

def test_resize_vectors():
 	for succeed, uut, din, imm, m, dout in CHECK_LIST1:
 		run_conversion(uut, False, wrapper, IMM = imm, MODE = m, DATA_IN = din, DATA_OUT = dout,
			display_module="$resize_vectors_add_1_3_24_24_8")
 		check_resize_vectors(succeed, uut, din, imm, m, dout)

