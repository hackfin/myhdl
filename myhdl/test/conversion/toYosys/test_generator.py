from myhdl import *

from .cosim_common import *
from .lfsr8 import lfsr8
from .test_simple import up_counter

t_state = enum("IDLE", "RUN", "WAIT", "RESET")
from .bitfields_simple import Bitfield

import pytest

BF_A = Bitfield(1, 2, 3)
BF_B = Bitfield(3, 5, 1)
BF_C = Bitfield(5, 7, 2)

@block
def bitfields(clk, ce, reset, dout, debug):
	"""Generator class test"""
	state = Signal(t_state.RESET)
	counter = Signal(modbv(0)[8:])

	ctr = up_counter(clk, ce, reset, counter)

	@always_seq(clk.posedge, reset)
	def fsm():
		if state == t_state.RESET:
			if BF_A(counter):
				state.next = t_state.WAIT
			else:
				state.next = t_state.RESET
		elif state == t_state.RUN:
			if BF_B(counter):
				if BF_A(counter):
					state.next = t_state.WAIT
			else:
				if BF_A(counter):
					state.next = t_state.RUN
		elif state == t_state.WAIT:
			if BF_C(counter):
				state.next = t_state.RUN
			else:
				state.next = t_state.IDLE
		else:
			state.next = t_state.RESET

	@always_comb
	def assign():
		dout.next = int(state) ^ counter

	return instances()

@block
def bitfields_inv(clk, ce, reset, dout, debug):
	"""Bitfield integer emulation test"""
	state = Signal(t_state.RESET)
	o = Signal(modbv(0)[8:])
	counter = Signal(modbv(0)[8:])

	ctr = up_counter(clk, ce, reset, counter)
	

	@always_seq(clk.posedge, reset)
	def fsm():
		if state == t_state.RESET:
			state.next = t_state.RUN
			o.next = int(BF_A | BF_B)
		elif state == t_state.RUN:
			o.next = int(BF_A)
			state.next = t_state.WAIT
		elif state == t_state.WAIT:
			o.next = int(BF_A | 1)
			state.next = t_state.IDLE
		else:
			state.next = t_state.RESET

	@always_comb
	def assign():
		dout.next = o ^ counter

	return instances()

@block
def bitfields_inv_val(clk, ce, reset, dout, debug):
	"""Bitfield integer emulation test"""
	state = Signal(t_state.RESET)
	o = Signal(modbv(0)[8:])
	counter = Signal(modbv(0)[8:])

	ctr = up_counter(clk, ce, reset, counter)
	
	@always_seq(clk.posedge, reset)
	def fsm():
		if state == t_state.RESET:
			state.next = t_state.RUN
			o.next = concat(intbv(BF_A.val)[3:], intbv(BF_B.val)[4:])
		elif state == t_state.RUN:
			o.next = BF_A.val
			state.next = t_state.WAIT
		elif state == t_state.WAIT:
			o.next = int(BF_A | 1)
			state.next = t_state.IDLE
		else:
			state.next = t_state.RESET

	@always_comb
	def assign():
		dout.next = o ^ counter

	return instances()

UUT_LIST = [  bitfields, bitfields_inv, bitfields_inv_val ]

@pytest.mark.parametrize("uut", UUT_LIST)
def test_mapped_uut(uut):
	arst = False
	# No wrapper, no display
	# 'check' command can crash in current yosys versions. Disabled for now
	run_conversion(uut, arst, None, False, run_check = False)
	run_tb(tb_unit(uut, mapped_uut, arst), 20000)


