from myhdl import *
from myhdl.conversion import yshelper
from synthesis.yosys.autowrap import autowrap, autowrap_unroll, unroll_bulk


@autowrap_unroll(unroll_bulk)
def DTR(STARTPULSE, DTROUT):
	"""Digital Temperature readout primitive"""

	dtrout = Signal(intbv()[8:])

	@always_comb
	def dummy():
		DTROUT.next = dtrout
		raise SystemError("Simulation model missing")

	return dummy

@autowrap
def JTAGG(TCK, TMS, TDI, TDO, JTDO1, JTDO2, JTDI, JTCK, JRTI1, JRTI2, JSHIFT,
	JUPDATE, JRSTN, JCE1, JCE2, \
	**parameters):

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


@autowrap
def GSR(gsr):
	"""GSR primitive"""

	@instance
	def dummy():
		pass

	return dummy

@autowrap
def PUR(gsr, RST_PULSE=1):
	"""PUR primitive"""

	@instance
	def dummy():
		pass

	return dummy

@autowrap
def DELAYF(A, LOADN, MOVE, DIRECTION, Z, CFLAG):
	"""Delay F element"""

	z, cflag = [ Signal(bool()) for i in range(2) ]

	@always_comb
	def dummy():
		Z.next = z
		CFLAG.next = cflag
		raise SystemError("Simulation model missing")

	return dummy

@autowrap
def DELAYG(A, Z):
	"""Delay G primitive"""

	z = Signal(bool())

	@always_comb
	def dummy():
		Z.next = z
		raise SystemError("Simulation model missing")

	return dummy

@autowrap
def USRMCLK(USRMCLKI, USRMCLKTS):
	"""User master clock primitive for SPI interface"""

	@instance
	def dummy():
		raise SystemError("Simulation model missing")

	return dummy

@autowrap
def IMIPI(A, AN, HSSEL, OHSOLS1, OLS0):
	"""MIPI auxiliary primitive"""

	ohsols1, ols0 = [ Signal(bool()) for i in range(2) ]

	@always_comb
	def dummy():
		OHSOLS1.next = ohsols1
		OLS0.next = ols0
		raise SystemError("Simulation model missing")

	return dummy



