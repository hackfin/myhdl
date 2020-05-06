# Arithmetic tests for yosys synthesis
#
#
# TODO TESTS:
#
# sb is signed signal:
#
# Test cases:  
#
# * a = sb[SLICE]
# * a = sb[SLICE].signed()
#
import myhdl
from myhdl import *
from .cosim_common import *
from .lfsr8 import lfsr8
import pytest
from random import randrange, seed


from myhdl import *

@block
def multiplier(clk, en, a, b, res):
    en1 = Signal(bool())
    
    @always(clk.posedge)
    def mul():
        if en:
            res.next = a * b

    return instances()

@block
def multiplier_explicit(clk, en, a, b, res):
    en1 = Signal(bool())
    
    @always(clk.posedge)
    def mul():
        if en:
            res.next = a.signed() * b.signed()

    return instances()

@block
def multiplier_tb(param, uut):
    size = param[0]
    w = 2 * size - 1
    size -= 1

    clk = Signal(bool())
    en = Signal(bool())
    a, b = [ Signal(intbv(0, min=-2**size, max=2**size)) for i in range(2) ]
    res = Signal(intbv(0, min=-2**w, max=2**w))

    inst_clkgen = clkgen(clk, 2)
    inst_uut = uut(clk, en, a, b, res)

    VALUES = [randrange(-127, 128) for i in range(256)]

    @instance
    def stim():
        en.next = False
        a.next = -2

        for _ in range(3):
            yield clk.posedge

        en.next = True

        last = 0

        for v in VALUES:
            b.next = v
            yield clk.posedge
            if int(res) != (-2 * last):
                print("is:  %d, should: %d" % (res, a * last))
                raise ValueError("Verification failed")
            last = v

        en.next = False

        raise StopSimulation
 
    return instances()

@block
def multiplier_unsigned_tb(param, uut):
    size = param[0]
    w = 2 * size

    clk = Signal(bool())
    en = Signal(bool())
    a, b = [ Signal(intbv(0)[size:]) for i in range(2) ]
    res = Signal(intbv(0)[w:])

    inst_clkgen = clkgen(clk, 2)
    inst_uut = uut(clk, en, a, b, res)

    VALUES = [randrange(0, 256) for i in range(256)]

    @instance
    def stim():
        en.next = False
        a.next = 3

        for _ in range(3):
            yield clk.posedge

        en.next = True

        last = 0

        for v in VALUES:
            b.next = v
            yield clk.posedge
            if int(res) != (a * last):
                print("is:  %d, should: %d" % (res, a * last))
                raise ValueError("Verification failed")
            last = v

        en.next = False

        raise StopSimulation
 
    return instances()




@block
def cosim_bench(uut, bench, param):
    """Cosimulation run for test benches that take a block as argument
    """

    wrapper = CosimObjectWrapper(uut, "clk,en,a,b,res")
    wrapper.trace = True # Trace
    wrapper.synth_pass = True # Run a synthesis pass
    inst_uut1 = bench(param, wrapper)
    inst_uut2 = bench(param, uut)

    return instances()

UUT_LIST = [ ( multiplier, multiplier_unsigned_tb, (8, )) ]
UUT_LIST += [ ( multiplier, multiplier_unsigned_tb, (32, )) ]
UUT_LIST += [ (multiplier_explicit, multiplier_tb, (8, )) ]
UUT_LIST += [ (multiplier, multiplier_tb, (8, )), (multiplier, multiplier_tb, (16, )) ]

# @pytest.mark.xfail
@pytest.mark.parametrize("uut,bench,param", UUT_LIST)
def test_memory_fail(uut, bench, param):
    seed(0)
    run_tb(cosim_bench(uut, bench, param), None)

