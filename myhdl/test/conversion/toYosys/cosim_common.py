# Cosimulation common routines for yosys backend tests
#

import myhdl
from myhdl import *

import os
path = os.path
import subprocess

from .lfsr8 import lfsr8
from myhdl._block import block, _Block

from myhdl.conversion import yshelper

def setupCosimulation(name, use_assert, interface, debug = False):
	tb = "tb_" + name
	objfile = "%s.o" % name
	if path.exists(objfile):
		os.remove(objfile)
	analyze_cmd = ['iverilog', '-g2012']
	analyze_cmd += ['-o', objfile, '%s.v' % name, '%s.v' % tb]
	if use_assert:
		analyze_cmd += ['aux/assert.v']
	# Don't involve technology specific mapping here:
	# analyze_cmd += ['techmap/cells_sim.v', '-I', 'techmap']
	subprocess.call(analyze_cmd)
	simulate_cmd = ['vvp', '-m', '../../../../cosimulation/icarus/myhdl.vpi']
	simulate_cmd += [ objfile ]
	if debug:
		print("Analyze command:", " ".join(analyze_cmd))
		print("Simulation command:", " ".join(simulate_cmd))

	c = Cosimulation(simulate_cmd, **interface)
	c.name = name
	return c

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
	dout, do_syn = [ Signal(modbv()[8:]) for i in range(2) ]
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
	del args['which']

	return setupCosimulation(name, False, args)


@block
def mapped_uut_assert(which, clk, ce, reset, dout, debug):
	args = locals()
	name = which.func.__name__ + "_mapped"
	del args['which']

	return setupCosimulation(name, True, args)



def design_from_entity(ent, async_reset = False, wrapper = None, **kwargs):
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
	if "run_check" in kwargs and kwargs["run_check"] == True:
		txt = design.run("check")
		if txt.find("Warning") >= 0:
			raise TypeError("Inconsitent In/Out mapping")
	design.write_verilog(name, True)
	if "test_syn" in kwargs and kwargs["test_syn"] == True:
		design.test_synth()
	return design

def run_tb(tb, cycles = 200000):
	tb.config_sim(backend = 'myhdl', timescale="1ps", trace=True)
	tb.run_sim(cycles)
	tb.quit_sim() # Quit so we can run another one

class CosimObjectWrapper:
	"""Cosimulation wrapper to allow arbitrary UUTs being called
from a uniform test bench interface"""
	def __init__(self, func, strargs, name = None, use_assert = False):
		self.func = func
		if name == None:
			name = func.__name__
		self.strargs = strargs
		self.name = name
		self.use_assert = use_assert
		self.design = yshelper.Design(name)
		self.synth_pass = False # Run a synthesis pass
		self.trace = False


	@block
	def __call__(self, *args, **kwargs):
		# Upon instancing the @block, this gets called and
		# generates a co-simulation verilog file on the fly
		l = self.strargs.split(',')
		name = self.func.__name__
		inst_uut = self.func(*args)
		inst_uut.convert("yosys_module", self.design, name=name, trace=self.trace)
		if self.synth_pass:
			self.design.test_synth()
		self.design.write_verilog(name, True)

		d = {}
		for e, i in enumerate(args):
			print("arg %d: %s" % (e, i))
			d[l[e]] = i

		return setupCosimulation(self.name + '_mapped', self.use_assert, d)

