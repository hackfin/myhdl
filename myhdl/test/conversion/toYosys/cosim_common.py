# Cosimulation common routines for yosys backend tests
#

import myhdl
from myhdl import *

from .util import setupCosimulation
from .lfsr8 import lfsr8

@block
def clkgen(clk, DELAY):
	@always(delay(DELAY))
	def clkgen():
		clk.next = not clk

	return instances()


@block
def tb_unit(uut, uut_syn, async_reset):
	clk = Signal(bool())
	debug, debug_syn = [ Signal(bool(0)) for i in range(2) ]
	ce = Signal(bool())
	dout, do_syn = [ Signal(intbv()[8:]) for i in range(2) ]
	reset = ResetSignal(0, 1, isasync = async_reset)

	inst_clkgen = clkgen(clk, 20)
	inst_uut = uut(clk, ce, reset, dout, debug)
	inst_syn = uut_syn(uut, clk, ce, reset, do_syn, debug_syn)

	r0, r1 = [ Signal(modbv()[8:]) for i in range(2) ]

	inst_lfsr0 = lfsr8(clk, 1, reset, 0, r0)

	@always_comb
	def assign():
		ce.next = r0[0]

	@instance
	def stimulus():
		# errcount = 0
		reset.next = 1
		yield(delay(200))
		reset.next = 0
		while 1:
			yield clk.posedge
			print(dout, debug, " --- ", do_syn, debug_syn)
			if dout != do_syn or debug != debug_syn:
				yield clk.posedge
				yield clk.posedge
				yield clk.posedge
				raise ValueError("Simulation mismatch")

	return instances()

@block
def mapped_uut(which, clk, ce, reset, dout, debug):
	args = locals()

	name = which.func.__name__ + "_mapped"

	tb = "tb_" + name

	return setupCosimulation(**locals())

@block
def mapped_wrapper(uut, clk, ce, reset, mode, data_out, data_in):
	"Cosimulation object for yosys post-synthesis(mapping) verilog output"
	args = locals()

	name = uut.__name__ + "_mapped"
	tb = "tb_" + name

	return setupCosimulation(**locals())

def design_from_entity(ent, async_reset = False, wrapper = None, **kwargs):
	from myhdl.conversion import yshelper
	clk = Signal(bool())
	debug = Signal(bool(0))
	ce = Signal(bool())
	reset = ResetSignal(0, 1, isasync = async_reset)

	if wrapper:
		DATA_IN = kwargs['DATA_IN']
		DATA_OUT = kwargs['DATA_OUT']
		MODE = kwargs['MODE']

		mode = Signal(MODE)
		data_in = Signal(modbv()[DATA_IN[1]:])
		data_out, data_check = [ Signal(modbv()[DATA_OUT[1]:]) for i in range(2) ]
		a = wrapper(ent, clk, ce, reset, mode, data_in, data_out, **kwargs)
		name = ent.func.__name__
		# name = "wrapper0"
	else:
		dout = Signal(intbv()[8:])
		a = ent(clk, ce, reset, dout, debug)
		name = ent.func.__name__

	design = yshelper.Design(name)

	# a.convert("verilog")
	a.convert("yosys_module", design, name=name, trace=True)

	return design

def run_conversion(ent, async_reset = False, wrapper = None, display = False, **kwargs):

	design = design_from_entity(ent, async_reset, wrapper, **kwargs)

	top = design.top_module()
	top_name = top.name.str()

	if display:
		if 'display_module' in kwargs:
			mname = kwargs['display_module']
		else:
			mname = top_name
		design.display_rtl(mname, fmt='dot')

	name = ent.func.__name__
	design.write_verilog(name, True)
	return design

def run_tb(tb, cycles = 200000):
	tb.config_sim(backend = 'myhdl', timescale="1ps", trace=True)
	tb.run_sim(cycles)
	tb.quit_sim() # Quit so we can run another one

