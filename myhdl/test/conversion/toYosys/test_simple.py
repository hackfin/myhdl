import myhdl
from myhdl import *

from .cosim_common import *

from .lfsr8 import lfsr8

@block
def up_counter(clk, ce, reset, counter):

	@always_seq(clk.posedge, reset)
	def worker():
		if ce:
			counter.next = counter + 1
		else:
			counter.next = counter

	return instances()

@block
def simple_expr(clk, ce, reset, dout, debug):
	counter = Signal(modbv(0)[8:])
	d = Signal(intbv(3)[2:])

	ctr = up_counter(clk, ce, reset, counter)

	@always_comb
	def assign():
		if counter % 4 == 0:
			dout.next = 1 | 4 | 2
		else:
			dout.next = 0

	return instances()


@block
def simple_arith(clk, ce, reset, dout, debug):
	counter = Signal(modbv(0)[8:])

	case = Signal(modbv()[8:])

	ctr = up_counter(clk, ce, reset, counter)

	@always_comb
	def modulo():
		case.next = counter % 8

	@always_comb
	def select():

		if counter > 80:
			if case == 0:
				dout.next = counter % 5
			elif case == 1:
				dout.next = counter[4:] * 2
			elif case == 2:
				dout.next = counter // 2
			else:
				dout.next = counter - 1

		else:
			dout.next = 0

	return instances()

@block
def simple_cases(clk, ce, reset, dout, debug):
	counter = Signal(modbv(0)[8:])

	ctr = up_counter(clk, ce, reset, counter)

	
	@always_comb
	def select():
		debug.next = counter[4]

		if counter == 14:
			dout.next = (counter & 0xf0) ^ 16 + 1
		elif counter == 15:
			dout.next = 18 // 3 # Integer division
		elif counter >= 25:
			dout.next = counter[3:] | 8
		elif counter == 26:
			dout.next = 1 | 2 | 8
		elif counter < 22:
			dout.next = (counter & 3) | 4
		else:
			dout.next = 0


	return instances()


@block
def simple_resize_cases(clk, ce, reset, dout, debug):
	counter = Signal(modbv(0)[8:])
	
	ctr = up_counter(clk, ce, reset, counter)

	@always_comb
	def select():
		debug.next = counter[4]

		if counter == 14:
			dout.next = counter[2:] | 16
		elif counter >= 25:
			dout.next = counter[4:2] | 8
		elif counter < 22:
			dout.next = counter[3:1] | 4
		else:
			dout.next = 0


	return instances()


@block
def counter_extended(clk, ce, reset, dout, debug):
	counter = Signal(modbv(0)[8:])
	x = Signal(modbv()[4:])
	y = Signal(modbv()[4:])

	d = Signal(intbv(3)[2:])
	
	@always_seq(clk.posedge, reset)
	def worker():
		if ce:
			debug.next = counter[4]
			counter.next = counter + 1
			d.next = 2
		else:
			d.next = 1
			debug.next = 0
			counter.next = counter

	@always_comb
	def select():
		if counter == 14:
			x.next = d + 1
			y.next = 2
		elif counter >= 118:
			x.next = (d - 1)
			y.next = 4
		elif counter < 22:
			x.next = 2
			y.next = 0
		else:
			if ce:
				x.next = 8
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

@block
def lfsr8_1(clk, ce, reset, dout, debug):
	"""LFSR with all states"""

	a, b = [ Signal(modbv()[8:]) for i in range(2) ]

	inst_lfsr = lfsr8(clk, ce, reset, 0, a)

	@always_comb
	def assign():
		dout.next = a

	return instances()


def test_counter():
	arst = True
	UNIT = counter_extended
	run_conversion(UNIT, arst)
	run_tb(tb_unit(UNIT, mapped_uut, arst), 22000)


def test_simple_expr():
	arst = False
	UNIT = simple_expr
	run_conversion(UNIT, arst)
	run_tb(tb_unit(UNIT, mapped_uut, arst), 2000)


def test_simple_arith():
	arst = False
	UNIT = simple_arith
	run_conversion(UNIT, arst)
	run_tb(tb_unit(UNIT, mapped_uut, arst), 22000)


def test_simple_cases():
	arst = True
	UNIT = simple_cases
	run_conversion(UNIT, arst)
	run_tb(tb_unit(UNIT, mapped_uut, arst), 22000)


def test_simple_resize():
	arst = True
	UNIT = simple_resize_cases
	run_conversion(UNIT, arst)
	run_tb(tb_unit(UNIT, mapped_uut, arst), 22000)

def test_lfsr():
	UNIT = lfsr8_1
	arst = False
	run_conversion(UNIT, arst)
	run_tb(tb_unit(UNIT, mapped_uut, arst), 2000)

if __name__ == '__main__':
	test_unit()

