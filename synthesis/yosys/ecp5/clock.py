# Clock management primitives ECP5
#
# (c) 2020 <hackfin@section5.ch>
#
#
from myhdl import *
from synthesis.yosys.autowrap import autowrap

from myhdl._Signal import _Signal

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

	sig_args = locals()
	sig_args.pop("parameters")

	@always_comb
	def assign():
		CLKINTFB.next = CLKFB
		REFCLK.next = CLKI
		CLKOP.next = CLKI
		CLKOS.next = CLKI
		CLKOS2.next = CLKI
		CLKOS3.next = CLKI
		INTLOCK.next = locked
		LOCK.next = locked

	@instance
	def sim():
		yield CLKI.posedge

		for i in range(20):
			yield CLKI.posedge
		locked.next = True
		
		print("Warning: Simulation model for EHXPLL missing")

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

	return sim, assign

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


