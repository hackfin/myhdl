# Clock management primitives ECP5
#
# (c) 2020 <hackfin@section5.ch>
#
#
from myhdl import *
from synthesis.yosys.autowrap import autowrap

from myhdl._Signal import _Signal

from .pllemu import VCOConfig, VCO, divider
# from pllemu_precise import VCO, divider

@autowrap
def CLKDIVF(CLKI, RST, ALIGNWD, CDIVX, **parameter):
	"Edge clock divider, see Lattice TN1263"
	CLKI.read = True
	if isinstance(RST, _Signal):
		RST.read = True
	if isinstance(ALIGNWD, _Signal):
		ALIGNWD.read = True

	@always_comb
	def assign():
		CDIVX.next = CLKI
		raise SystemError("Simulation model missing")

	return assign

@autowrap
def DCCA(CLKI, CE, CLKO):

	clko = Signal(bool())

	@always_comb
	def dummy():
		CLKO.next = clko
		raise SystemError("Simulation model missing")

	return dummy

@autowrap
def DCSC(CLK0, CLK1, SEL, MODESEL, DCSOUT, DCSMODE = "POS"):

	dcsout = Signal(bool())

	@always_comb
	def dummy():
		DCSOUT.next = dcsout
		raise SystemError("Simulation model missing")

	return dummy

@autowrap
def DLLDELD(A, DDRDEL, LOADN, MOVE, DIRECTION, Z, CFLAG):
	z = Signal(bool())
	cflag = Signal(bool())

	@always_comb
	def dummy():
		Z.next = z
		CFLAG.next = cflag
		raise SystemError("Simulation model missing")

	return dummy

@autowrap
def ECLKBRIDGECS(CLK0, CLK1, SEL, ECSOUT):

	ecsout = Signal(bool())

	@always_comb
	def dummy():
		ECSOUT.next = ecsout
		raise SystemError("Simulation model missing")

	return dummy

@autowrap
def EHXPLLL(CLKI, CLKFB, PHASESEL1, PHASESEL0, PHASEDIR, PHASESTEP, \
	PHASELOADREG, STDBY, \
	PLLWAKESYNC, RST, ENCLKOP, ENCLKOS, ENCLKOS2, ENCLKOS3, \
	CLKOP, CLKOS, CLKOS2, CLKOS3, LOCK, INTLOCK, \
	REFCLK, CLKINTFB, \
	**parameters):

	locked = Signal(bool())
	vco_clk = Signal(bool())

	clkop, clkos, clkos2, clkos3 = [ Signal(bool()) for _ in range(4) ]

	sig_args = locals()
	sig_args.pop("parameters")

	print("VCO div: %d mul: %d" % (parameters['CLKFB_DIV'], parameters['CLKI_DIV']))
	cfg = VCOConfig(100.0, parameters['CLKFB_DIV'], parameters['CLKI_DIV'])
	vco_inst = VCO(CLKI, RST, vco_clk, locked, cfg.divref, cfg.net_divide)

	clkdiv_inst = []

	if ENCLKOP:
		d = parameters['CLKOP_DIV'] - 1
		print("Enable CLKOP with divider %d" % d)
		clkop_inst = divider(vco_clk, RST, d, clkop)
		clkdiv_inst.append(clkop_inst)
	if ENCLKOS:
		d = parameters['CLKOS_DIV'] - 1
		print("Enable CLKOS with divider %d" % d)
		clkos_inst = divider(vco_clk, RST, d, clkos)
		clkdiv_inst.append(clkos_inst)
	if ENCLKOS2:
		d = parameters['CLKOS2_DIV'] - 1
		print("Enable CLKOS2 with divider %d" % d)
		clkos2_inst = divider(vco_clk, RST, d, clkos2)
		clkdiv_inst.append(clkos2_inst)
	if ENCLKOS3:
		d = parameters['CLKOS3_DIV'] - 1
		print("Enable CLKOS3 with divider %d" % d)
		clkos3_inst = divider(vco_clk, RST, d, clkos3)
		clkdiv_inst.append(clkos3_inst)


	@always_comb
	def assign():
		# Explicit assignments to make sure I/O are resolved
		CLKINTFB.next = CLKFB
		CLKOP.next = clkop
		CLKOS.next = clkos
		CLKOS2.next = clkos2
		CLKOS3.next = clkos3
		REFCLK.next = vco_clk
		INTLOCK.next = locked
		LOCK.next = locked


	# @default_parameters
	def parameters():
		"Defaults. Currently not needed, just left for documentation"
		return {
			"CLKI_DIV" : 1,
			"CLKFB_DIV" : 1,
			"CLKOP_DIV" : 1,
			"CLKOS_DIV" : 1,
			"CLKOS2_DIV" : 1,
			"CLKOS3_DIV" : 1,
			"CLKOP_ENABLE" : "ENABLED",
			"CLKOS_ENABLE" : "DISABLED",
			"CLKOS2_ENABLE" : "DISABLED",
			"CLKOS3_ENABLE" : "DISABLED",
			"CLKOP_CPHASE" : 0,
			"CLKOS_CPHASE" : 0,
			"CLKOS2_CPHASE" : 0,
			"CLKOS3_CPHASE" : 0,
			"CLKOP_FPHASE" : 0,
			"CLKOS_FPHASE" : 0,
			"CLKOS2_FPHASE" : 0,
			"CLKOS3_FPHASE" : 0,
			"FEEDBK_PATH" : "CLKOP",
			"CLKOP_TRIM_POL" : "RISING",
			"CLKOP_TRIM_DELAY" : 0,
			"CLKOS_TRIM_POL" : "RISING",
			"CLKOS_TRIM_DELAY" : 0,
			"OUTDIVIDER_MUXA" : "DIVA",
			"OUTDIVIDER_MUXB" : "DIVB",
			"OUTDIVIDER_MUXC" : "DIVC",
			"OUTDIVIDER_MUXD" : "DIVD",
			"PLL_LOCK_MODE" : 0,
			"PLL_LOCK_DELAY" : 200,
			"REFIN_RESET" : "DISABLED",
			"SYNC_ENABLE" : "DISABLED",
			"INT_LOCK_STICKY" : "ENABLED",
			"DPHASE_SOURCE" : "DISABLED",
			"STDBY_ENABLE" : "DISABLED",
			"PLLRST_ENA" : "DISABLED",
			"INTFB_WAKE" : "DISABLED"
		}

	return clkdiv_inst, vco_inst, assign

@autowrap
def DCCA(CLKI, CE, CLKO):

	clko = Signal(bool())

	@always_comb
	def dummy():
		CLKO.next = clko
		raise SystemError("Simulation model missing")

	return dummy

@autowrap
def OSCG(OSC, **parameter):
	"On-Chip oscillator"
	
	# half period in pico seconds
	C_OSCP = 1613
	oscb = Signal(bool(0))

	try:
		DIV = parameter['DIV']
	except KeyError:
		print("No 'DIV' parameter given for divider, using default 128")
		DIV = 128

	halfp = C_OSCP * DIV

	@instance
	def sim():
		while 1:
			yield delay(halfp)
			oscb.next = not oscb

	@always_comb
	def assign():
		OSC.next = oscb
	
	return sim, assign

@autowrap
def PLLREFCS(CLK0, CLK1, SEL, PLLCSOUT):

	pllcsout = Signal(bool())

	@always_comb
	def dummy():
		PLLCSOUT.next = pllcsout
		raise SystemError("Simulation model missing")

	return dummy

@autowrap
def EXTREFB(REFCLKP, REFCLKN, REFCLKO, **parameter):

	refclko = Signal(bool())

	@always_comb
	def emulate():
		REFCLKO.next = REFCLKP and not REFCLKN

	return emulate


