from __future__ import absolute_import
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

def test_counter():
	UNIT = counter_extended
	arst = True

	run_conversion(UNIT, arst)
	run_tb(tb_unit(UNIT, mapped_uut, arst))
	return True

if __name__ == '__main__':
	test_counter()

