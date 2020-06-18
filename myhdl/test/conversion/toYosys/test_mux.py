import myhdl
from myhdl import *
from .cosim_common import *
from .lfsr8 import lfsr8
import pytest
from .test_simple import up_counter


@block
def defaults1(clk, ce, reset, dout, debug):
	"Working test case"
	counter = Signal(modbv(0)[8:])
	cr = ResetSignal(0, 1, isasync = False)
	ctr = up_counter(clk, ce, reset, counter)

	cbits = [ counter(i) for i in range(len(counter)) ]

	data = ConcatSignal(*cbits)

	@always_comb
	def assign():
		dout.next = 0xff
		if counter < 5:
			if ce:
				dout.next = 1

		elif counter > 20:
			dout.next = 2


	return instances()

OPCODE = slice(5, 3)
MODE   = slice(3, 1)
FLAG   = 0

@block
def defaults2(clk, ce, reset, dout, debug):
	"Test case with implicit assingments"
	counter = Signal(modbv(0)[8:])

	ctr = up_counter(clk, ce, reset, counter)

	@always_comb
	def worker():
		op = counter[OPCODE]
		k = counter[MODE]
		f = counter[FLAG]

		debug.next = 0
		dout.next = 0x51
		if op == 0b00:
			if ce:
				dout.next = 0xaa
			else:
				dout.next = 0xf0
		elif op == 0b01:
			# dout.next = 0x51
			debug.next = 0
			if k == 0:
				if f:
					debug.next = 1
					dout.next = 0x50
				else:
					debug.next = 0
					dout.next = 0x10
			elif k == 2:
				dout.next = 0x51
			else:
				# dout.next = 0x51
				pass
			# Implicit other = 0x51
		elif op == 0b10:
			dout.next = 0xfa
		else: 
			dout.next = 0xff

	return instances()

t_state = enum("RESET", "RUN", "IDLE", "WAIT")

@block
def defaults3(clk, ce, reset, dout, debug):
	"Complex FSM test case with implicit default coverage"
	counter = Signal(modbv(0)[8:])
	state = Signal(t_state.RESET)
	cr = ResetSignal(0, 1, isasync = False)

	ctr = up_counter(clk, ce, cr, counter)

	def _int(x):
		return intbv(x)[8:]

	@always_seq(clk.posedge, reset)
	def fsm():
		isdebug = True
		# Required default
		v = _int(0xff)
		if ce:
			if state == t_state.RESET:
				if counter == 10:
					state.next = t_state.WAIT
			elif state == t_state.RUN:
				v = _int(12)
				if counter == 41:
					state.next = t_state.WAIT
			elif state == t_state.WAIT:
				# Note: We omit v assignment, assuming 0xff default
				isdebug = False
				state.next = t_state.IDLE
			else:
				v = _int(2)
				if counter > 20:
					state.next = t_state.RUN
					v = _int(11)

		debug.next = isdebug
		dout.next = v

	@always_comb
	def assign():
		cr.next = (state == t_state.WAIT) | reset

	return instances()

@block
def complex_select(clk, ce, reset, dout, debug):
	"Complex selection test"

	counter = Signal(modbv(0)[8:])
	cr = ResetSignal(0, 1, isasync = False)

	ctr = up_counter(clk, ce, cr, counter)

	@always_comb
	def worker():
		op = counter[OPCODE]
		k = counter[MODE]
		f = counter[FLAG]

		isdebug = False

		if op == 0b00:
			if ce:
				dout.next = 0xaa
			else:
				dout.next = 0xff
		elif op == 0b01:
			if k == 0:
				if f:
					isdebug = True
					dout.next = 0x50
				else:
					dout.next = 0x10
			elif k == 2:
				dout.next = 0x51
			else:
				dout.next = 0x55
		elif op == 0b10:
			dout.next = 0xfa
		else: 
			dout.next = 0xff

		debug.next = isdebug

	@always_comb
	def assign():
		cr.next = reset

	return instances()


@block
def no_default(clk, ce, reset, dout, debug):
	"MUX case with missing default statement"
	counter = Signal(modbv(0)[8:])
	@always_seq(clk.posedge, reset)
	def worker():
		if ce:
			counter.next = counter + 1

	@always_comb
	def assign():
		if counter == 0:
			dout.next = 20
			debug.next = False
		elif counter <= 15:
			dout.next = 21
			debug.next = True
		# Missing else:

	return instances()

@block
def var_mux(clk, ce, reset, dout, debug):
	"Case with wrong bit width initialization"
	o = Signal(modbv()[8:])
	inst_lfsr1 = lfsr8(clk, 1, reset, 0, o)

	@always_seq(clk.posedge, reset)
	def worker():
		v = 6
		if o == 33:
			v = 4
		else:
			v = 0xff

		dout.next = v

	return instances()

@block
def var_pmux(clk, ce, reset, dout, debug):

	o = Signal(modbv()[8:])
	inst_lfsr1 = lfsr8(clk, ce, reset, 0, o)

	@always_seq(clk.posedge, reset)
	def worker():

		v = 0xff

		if o == 3:
			if o[1]:
				if ce:
					v = 1
			elif o[0]:
				if ce:
					v = 14
		elif o == 1:
			v = 2
		else:
			v = 0

		dout.next = v
		debug.next = o[2]

	return instances()

@block
def pitfall_redef(clk, ce, reset, dout, debug):
	"""Do we allow this?"""
	state = Signal(intbv(0)[5:])

	@always_seq(clk.posedge, reset)
	def worker():

		v = 0xff

		if state == 2:
			dout.next = 1

		if state == 0:
			state.next = 1
		elif state == 1:
			pass
		else:
			debug.next = ce
			state.next = 0
			dout.next = v

	return instances()


UUT_LIST = [ defaults1, defaults2, defaults3, complex_select ]

UUT_LIST += [ no_default ]


@pytest.mark.parametrize("uut", UUT_LIST)
def test_mux(uut):
	arst = False
	run_conversion(uut, arst, None, False) # No wrapper, no display
	run_tb(tb_unit(uut, mapped_uut, arst), 20000)


UUT_BROKEN_LIST = [ var_mux, var_pmux, pitfall_redef  ]

@pytest.mark.xfail
@pytest.mark.parametrize("uut", UUT_BROKEN_LIST)
def test_mux_broken(uut):
	arst = False
	run_conversion(uut, arst, None, False) # No wrapper, no display
	run_tb(tb_unit(uut, mapped_uut, arst), 200)

