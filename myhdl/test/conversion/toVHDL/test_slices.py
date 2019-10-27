from myhdl import *
from myhdl.conversion import verify

"""Test case #<ISSUE_NUMBER> (hackfin@section5.ch)

Python slice types did not convert so far. However, they are a conventient
auxiliary when designing CPUs and slicing portions out of instruction words.

This test verifies that slices convert properly, for example constructs as:

	SLICE_IMMEDIATE = slice(10, 2)
	...
	imm.next = insn[SLICE_IMMEDIATE]

"""

t_slmode = enum('SL_UNSIGNED', 'SL_SIGNED')

SL_UPPER = 15
SL_LOWER = 8
SLICE_0 = slice(SL_UPPER, SL_LOWER)

CHECK_LIST = (
#         input       mode                  slice         result
		( 0xbeef,     t_slmode.SL_UNSIGNED, slice(9, 0),  0xef ),
		( 0xbeef,     t_slmode.SL_SIGNED,   slice(8, 0),  0xffffffef ),
		( 0x8fbeef00, t_slmode.SL_UNSIGNED, slice(24, 8), 0xbeef ),
		( 0x8fbeef00, t_slmode.SL_SIGNED,   slice(24, 8), 0xffffbeef ),
)


CHECK_LIST_FUNC = (
		( 0xdeadbeef, t_slmode.SL_UNSIGNED, None, 0xefde ),
		( 0xfaced00f,   t_slmode.SL_UNSIGNED, None, 0x0ffa ),
		( 0xfaced08f,   t_slmode.SL_SIGNED, None, 0x8ffa ),
)

def slice_vectors(clk, SLICE, mode, data_out, data_in):
	"Resize signed and unsigned test case"

	@always_comb
	def worker():
		if mode == t_slmode.SL_SIGNED:
			data_out.next = data_in[SLICE].signed()
		else:
			data_out.next = data_in[SLICE]

	return instances()

def to_fract0(val, pos, l):
	"""This is the case where a vector of fixed size (l) should be returned.
When assigning a variable to this return that assumes a fixed length,
this is the call to make."""
	v = modbv(val[pos:pos-l])
	return v

def to_fract1(val, pos, l):
	"""This returns a vector with the length of 'val'.
When assigning a variable to it that should have a specific length (like
for example when an argument to contatenation) this will go wrong."""
	return val[pos:pos-l]

def to_fract_s(val, pos, l):
	"""Version for signed type"""
	v = modbv(val[pos:pos-l])
	return v.signed()

def slice_vectors_func(clk, mode, data_out, data_in, f_convert):
	"Resize signed and unsigned test case"

	tmp = Signal(modbv()[32:])
	

	@always_comb
	def worker():
		v = f_convert(data_in, 32, 8)
		u = f_convert(data_in, 8, 8)

		if mode == t_slmode.SL_SIGNED:
			t = data_in.signed()
			v = f_convert(t, 32, 8)
			u = f_convert(t, 8, 8)

		vs = to_fract_s(data_in, 16, 8)

		tmp[15:8].next = 20

		invalid = to_fract1(data_in, 16, 8)

		data_out.next = concat(u, v)

	return instances()


def tb_slice(DATA_IN, MODE, SLICE, DATA_OUT):

	data_in, data_out, data_check = [ Signal(modbv()[32:]) for i in range(3) ]
	data_in1, data_out1, data_check1 = [ Signal(modbv()[12:]) for i in range(3) ]
	mode = Signal(t_slmode.SL_UNSIGNED)
	clk = Signal(bool(0))

	inst_uut = slice_vectors(clk, SLICE, mode, data_out, data_in)

	@instance
	def clkgen():
		while 1:
			yield delay(10)
			clk.next = not clk

	@instance
	def stimulus():
		data_in.next = DATA_IN
		data_check.next = DATA_OUT
		mode.next = MODE
		yield clk.posedge
		yield clk.posedge
		if data_out == data_check:
			print("PASS: case: %s" % mode)
			pass
		else:
			raise ValueError("resize error, result %x" % data_out)

		raise StopSimulation

	return instances()

def tb_slice_func(DATA_IN, MODE, SLICE, DATA_OUT, f_convert):
	data_in = Signal(modbv()[32:])
	data_out, data_check = [ Signal(modbv()[16:]) for i in range(2) ]
	mode = Signal(t_slmode.SL_UNSIGNED)
	clk = Signal(bool(0))

	inst_uut = slice_vectors_func(clk, mode, data_out, data_in, f_convert)

	@instance
	def clkgen():
		while 1:
			yield delay(10)
			clk.next = not clk

	@instance
	def stimulus():
		data_in.next = DATA_IN
		data_check.next = DATA_OUT
		mode.next = MODE
		yield clk.posedge
		yield clk.posedge
		if data_out == data_check:
			print("PASS: case: %s" % mode)
			pass
		else:
			print("FAIL: data out: %s" % data_out)
			raise ValueError("resize error, result %x" % data_out)

		raise StopSimulation

	return instances()


def check_slice(din, mode, sl, dout):
	assert verify(tb_slice, din, mode, sl, dout) == 0

def check_slice_func(din, mode, sl, dout, f_conv):
	assert verify(tb_slice_func, din, mode, sl, dout, f_conv) == 0

def test_slice():
	for din, mode, sl, dout in CHECK_LIST:
		yield check_slice, din, mode, sl, dout

def test_slice_func():
	"Test slice functions"
	CORRECT_FUNC = to_fract0
	WRONG_FUNC = to_fract1
	for din, mode, sl, dout in CHECK_LIST_FUNC:
		yield check_slice_func, din, mode, sl, dout, CORRECT_FUNC

if __name__ == '__main__':
	data_in, data_out, data_check = [ Signal(intbv()[12:]) for i in range(3) ]
	mode = Signal(t_slmode.SL_UNSIGNED)
	clk = Signal(bool(0))

	# toVHDL(slice_vectors_func, clk, mode, data_out, data_in, to_fract0)
	inst = slice_vectors_func(clk, mode, data_out, data_in, to_fract0)
	inst.convert("VHDL")
