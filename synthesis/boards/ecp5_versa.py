# Board supply package for Versa ECP5 board
#
# (c) 2020 section5.ch
#

"""A board supply package is implemented as a class inheriting from
both:

 * The BoardSupplyPackage based class
 * A synthesis rules class, based on yshelper.YosysInferenceRule
"""

from myhdl.conversion.yshelper import BoardSupplyPackage

from ..yosys.ecp5.rules import SynthesisRulesECP5

class bsp(BoardSupplyPackage, SynthesisRulesECP5):
	"Board supply for ECP5 Versa eval kit"
	def __init__(self):
		SynthesisRulesECP5.__init__(self)
