import myhdl
from myhdl import *

from .cosim_common import *

@block
def counter_extended(clk, ce, reset, dout, debug):
	counter = Signal(modbv(0)[8:])
	x = Signal(modbv()[2:])
	y = Signal(modbv()[2:])

	d = Signal(intbv(3)[2:])
	
	@always_seq(clk.posedge, reset)
	def worker():
		if ce:
			debug.next = counter[4]
			counter.next = counter + 1
			d.next = 1
		else:
			debug.next = 0
			counter.next = counter

	@always_comb
	def select():
		if counter == 14:
			x.next = d + 1
			y.next = 2
		elif counter == 118:
			x.next = d - 1
			y.next = 1
		elif counter == 22:
			x.next = 2
			y.next = 0
		else:
			if ce:
				x.next = 0
				y.next = 3
			else:
				x.next = 1
				y.next = 1

	@always_comb
	def assign():
		dout.next = x ^ y

	return instances()


@block
def lfsr8_0(clk, ce, reset, dout, debug):
	"""LFSR with all states"""
	x = Signal(modbv(0)[8:])
	f = Signal(bool())

	@always_seq(clk.posedge, reset)
	def worker():
		if ce == 1:
			x.next = concat(x[6], x[5], x[4], x[3] ^ f, x[2] ^ f, x[1] ^ f, x[0], f)

	@always_comb
	def assign():
		e = x[7:0] == 0
		f.next = x[7] ^ e
		dout.next = x

	return instances()


def test_unit():
	UNIT = lfsr8_0
	arst = True
	run_conversion(UNIT, arst)
	run_tb(tb_unit(UNIT, mapped_uut, arst), 200)

	UNIT = counter_extended
	run_conversion(UNIT, arst)
	run_tb(tb_unit(UNIT, mapped_uut, arst), 200)
	return True

if __name__ == '__main__':
	test_unit()

