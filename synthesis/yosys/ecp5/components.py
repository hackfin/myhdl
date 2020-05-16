# ECP5 components
#
# translated to MyHDL <hackfin@section5.ch>
#
# Note: all signals must be arguments, all parameters are a keyword
# list at the end. UNSTABLE, this API may change.

from myhdl import *
from myhdl.conversion import yshelper
from synthesis.yosys.autowrap import autowrap


@autowrap
def OSCG(OSC, **parameter):
	"On-Chip oscillator"
	C_OSCP = 1.613
	oscb = Signal(bool(0))

	try:
		DIV = parameter['DIV']
	except KeyError:
		print("BAD divider, using default 128")
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
		yield delay(CLKI.posedge)

		for i in range(20):
			yield delay(CLKI.posedge)
		locked.next = True
		
		print("Warning: Simulation model missing")

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
def JTAGG(TCK, TMS, TDI, TDO, JTDO1, JTDO2, JTDI, JTCK, JRTI1, JRTI2, JSHIFT,
	JUPDATE, JRSTN, JCE1, JCE2, \
	**parameters):

	locked = Signal(bool())

	sig_args = locals()
	sig_args.pop("parameters")

	TCK.read = True
	TMS.read = True
	TDI.read = True
	JTDO1.read = True
	JTDO2.read = True

	@always(TCK.posedge)
	def bypass():
		"Simple bypass forwarding"
		TDO.next = TDI

	@always_comb
	def assign():
		JTDO1.next = True
		JTDO2.next = True
		JTDI.next = TDI
		JTCK.next = True
		JRTI1.next = True
		JRTI2.next = True
		JSHIFT.next = True
		JUPDATE.next = True
		JRSTN.next = True
		JCE1.next = True
		JCE2.next = True


	return bypass, assign

