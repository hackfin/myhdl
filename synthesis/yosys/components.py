# ECP5 components
#
# translated to MyHDL <hackfin@section5.ch>
#

from myhdl import *
from myhdl.conversion import yshelper
from synthesis.autowrap import autowrap

@autowrap
def EHXPLLL(clki, clkfb, clkop, clkos, clkos2, clkos3, lock, intlock, \
	**parameters):

	locked = Signal(bool())

	sig_args = locals()
	sig_args.pop("parameters")

	clkfb.read = True

	@always_comb
	def assign():
		clkop.next = clki
		clkos.next = clki
		clkos2.next = clki
		clkos3.next = clki
		lock.next = locked

	@instance
	def sim():
		yield delay(clki.posedge)

		for i in range(20):
			yield delay(clki.posedge)
		locked.next = True
		
		print("Warning: Simulation model missing")

	return sim, assign
