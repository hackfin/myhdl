# Simple PLL emulation in MyHDL
#
#
# (c) section5.ch
#
# This file is under GNU Public license v2
# 
# 

from myhdl import *
from synthesis.yosys.autowrap import autowrap

simulation_only = blackbox

@simulation_only
def divider(clk, rst, div, div_out):
	count = Signal(intbv())
	outdiv = Signal(bool())

	@always(clk)
	def worker():
		count.next = count + 1
		if count == div:
			div_out.next = not div_out
			count.next = 0

	return instances()

EPSILON = 1

class Shared:
	"Shared float variables"
	def __init__(self):
		self.t_diva_clk = 0.0
		self.t_divb_clk = 0.0
		self.t_divc_clk = 0.0
		self.t_divd_clk = 0.0

class VCOConfig:
	"VCOConfig variables"
	precise = False

	def __init__(self, clkfreq_mhz, refdiv, mul):
		# Period in picoseconds:
		self.clki_halfperiod = int(500000.0 / clkfreq_mhz)
		self.divref = refdiv
		self.net_divide = int(mul)

@simulation_only
def VCO(clk, reset, clko, valid, DIVREF, MULTIPLIER):
	"""Emulation of Voltage controlled oscillator"""
	first, repeat, trigger = [ Signal(bool(0)) for _ in range(3) ]

	clock_valid, clock_invalid = [ Signal(bool(0)) for _ in range(2) ]

	lastedge, edge = [ Signal(intbv()) for _ in range(2) ]
	count0, count1 = [ Signal(intbv(0)[20:]) for _ in range(2) ]

	deltas = [ Signal(intbv()) for _ in range(4) ]

	clk_vco = Signal(bool(0), delay=2)

	@always(clk)
	def worker():
		# This has the behaviour of a synchronous reset:
		if reset:
			first.next = False
			clock_valid.next = False
		else:
			lastedge.next = edge
			edge.next = now()
			# Time delta chain
			delta_t = edge - lastedge
			deltas[0].next = delta_t
			deltas[1].next = deltas[0]
			deltas[2].next = deltas[1]
			deltas[3].next = deltas[2]
			
			if delta_t > 0:
				jitter_t1 = deltas[0] - deltas[1]
				jitter_t2 = deltas[1] - deltas[2]
				jitter_t3 = deltas[2] - deltas[3]

				if abs(jitter_t1) < EPSILON and abs(jitter_t2) < EPSILON and abs(jitter_t3) < EPSILON:
					clock_valid.next = True
				else:
					clock_valid.next = False

				if abs(jitter_t1 < EPSILON):
					clock_invalid.next = False
				else:
					clock_invalid.next = True
		
				# Calc half period:
				t_vco = float(delta_t) * float(DIVREF) / float(MULTIPLIER)

				first.next = True
				# We neglect the rounding errors for now:
				if t_vco < 1:
					raise ValueError("Time step not sufficiently small for period %f" % t_vco)
				clk_vco.delay = int(t_vco)
			else:
				first.next = False


	@always_comb
	def assign():
		trigger.next = first
		valid.next = clock_valid
		clko.next = clk_vco

	@always(clk_vco, trigger)
	def vco_clkgen():
		clk_vco.next = not clk_vco


	return instances()

@blackbox
def pll_example(cfg, clka, clkb):
	"""PLL example for two output clocks"""
	clk = Signal(bool(0))
	vco_valid = Signal(bool())
	vcoreset = Signal(bool())
	vco_clk = Signal(bool())
	reset = ResetSignal(1, 1, True)

	vco_inst = VCO(clk, reset, vco_clk, vco_valid, cfg.divref, cfg.net_divide)

	diva_inst = divider(vco_clk, reset, 16-1, clka)
	divb_inst = divider(vco_clk, reset, 12-1, clkb)

	@always_comb
	def assign_reset():
		vcoreset.next = reset

	@always(delay(cfg.clki_halfperiod))
	def clkgen():
		clk.next = not clk

	@instance
	def stim():
		yield delay(10)
		reset.next = 0
		
	@instance
	def startup():
		yield delay(200)
		reset.next = True
		yield clk.posedge
		reset.next = False

	return instances()

if __name__ == '__main__':
	# Configure VCO:
	cfg = VCOConfig(100.0, 1, 4)
	diva_clk, divb_clk = [ Signal(bool(0)) for _ in range(2) ]
	p = pll_example(cfg, diva_clk, divb_clk)
	p.config_sim(name="pll", backend = 'myhdl', timescale = '1ps', trace = True)
	p.run_sim(1000000)
	p.quit_sim()

