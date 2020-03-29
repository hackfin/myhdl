from myhdl import *

"""Test case #<ISSUE_NUMBER> (hackfin@section5.ch)

Forbidden constructs

Stuff that should throw a warning if not making sense.

"""

CHECK_LIST = (
		( 0xdeadbeef, 0,  0xffef ),
		# The next 'wrong' results are satisfied to exhibit ghdl messages on
		# (expected) bound check failures:
		( 0xdeadbeef, 1,  0xffff ),  # This is an incorrect result, but the
                                     # MyHDL simulator will produce that
		( 0xdeadbeef, 2,  0xffff ),  # .. likewise.
)

SLICE = slice(16, 8)

@block
def slice_assign_wrong(clk, mode, data_out, data_in, dummy):
	"Resize signed and unsigned test case"

	@always(clk.posedge)
	def worker():
		data_out.next = 0xffff
		# These constructs convert to VHDL, but size to
		# the actual signal size, not the slice size:
		if mode == 1:
			data_out[SLICE].next = data_in[8:0] # Bad size (bound check failure)
		elif mode == 2:
			data_out[8:0].next = data_in[8:0]   # Bad size
		else:
			data_out.next[8:0] = data_in[8:0]   # Correct

	return instances()

@block
def tb_forbidden(DATA_IN, MODE, DATA_VERIFY, f_convert, uut):
	data_in = Signal(modbv()[32:])
	data_out, data_check = [ Signal(modbv()[16:]) for i in range(2) ]
	mode = Signal(intbv()[4:])
	clk = Signal(bool(0))

	inst_uut = uut(clk, mode, data_out, data_in, f_convert)

	@instance
	def clkgen():
		while 1:
			yield delay(10)
			clk.next = not clk

	@instance
	def stimulus():
		data_in.next = DATA_IN
		data_check.next = DATA_VERIFY
		mode.next = MODE
		yield clk.posedge
		yield clk.posedge
		if data_out == data_check:
			print("PASS: case: %s" % mode)
			pass
		else:
			print("FAIL: data out: %s" % data_out)
			raise ValueError("slice error, result %x" % data_out)

		raise StopSimulation

	return instances()

def check_slice_assign(din, mode, dout, f_conv, uut):
	tb = tb_forbidden(din, mode, dout, f_conv, uut)
	try:
		assert tb.verify_convert() == 0
		print("We should not get here")
		# assert False
	except TypeError:
		assert True
	

def test_slice_assign_broken():
	for din, mode, dout in CHECK_LIST:
		yield check_slice_assign, din, mode, dout, None, slice_assign_wrong

