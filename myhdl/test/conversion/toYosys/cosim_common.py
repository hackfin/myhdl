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
	dout, do_syn = [ Signal(intbv()[2:]) for i in range(2) ]
	reset = ResetSignal(0, 1, isasync = async_reset)

	inst_clkgen = clkgen(clk, 20)
	inst_uut = uut(clk, ce, reset, dout, debug)
	inst_syn = uut_syn(uut, clk, ce, reset, do_syn, debug_syn)

	r0, r1 = [ Signal(modbv()[8:]) for i in range(2) ]

	inst_lfsr0 = lfsr8(clk, reset, 0, 1, r0)

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

	tb = "lib/tb_unit_mapped"
	name = which.func.__name__ + "_mapped"

	return setupCosimulation(**locals())


def run_conversion(ent, async_reset):
	from myhdl.conversion import yshelper
	clk = Signal(bool())
	debug = Signal(bool(0))
	ce = Signal(bool())
	dout = Signal(intbv()[2:])
	reset = ResetSignal(0, 1, isasync = async_reset)

	a = ent(clk, ce, reset, dout, debug)

	design = yshelper.Design("test")

	# a.convert("verilog")
	a.convert("yosys_module", design)

	# design.display_rtl()
	design.write_verilog(ent.func.__name__, True)


def run_tb(tb):
	tb.config_sim(backend = 'myhdl', timescale="1ps", trace=True)
	tb.run_sim(200000)

