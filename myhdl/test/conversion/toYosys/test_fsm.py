# FSM tests for toYosys conversion
#

import myhdl
from myhdl import *
from .cosim_common import *
from .lfsr8 import lfsr8
import pytest
from .test_simple import up_counter

t_state = enum("IDLE", "RUN", "WAIT", "RESET")

@block
def complex_fsm(clk, ce, reset, dout, debug):
    "Complex FSM test case with explicit state assignment coverage"
    counter = Signal(modbv(0)[8:])
    o = Signal(modbv(0)[8:])
    state = Signal(t_state.RESET)
    cr = ResetSignal(0, 1, isasync = False)

    a = 144

    inst_lfsr = lfsr8(clk, ce, reset, 0, o)

    ctr = up_counter(clk, ce, cr, counter)

    @always_seq(clk.posedge, reset)
    def fsm():
        if state == t_state.RESET:
            if counter == 10:
                state.next = t_state.WAIT
            else:
                state.next = t_state.RESET
        elif state == t_state.RUN:
            if counter == 30:
                if o[0] == 1:
                    state.next = t_state.WAIT
                else:
                    state.next = t_state.IDLE
            else:
                if counter > 40:
                    state.next = t_state.WAIT
                else:
                    state.next = t_state.RUN
        elif state == t_state.WAIT:
            if o[0]:
                state.next = t_state.RUN
            else:
                state.next = t_state.IDLE
        else:
            if counter > 20:
                state.next = t_state.RUN
            else:
                state.next = t_state.IDLE

    @always_comb
    def assign():
        dout.next = counter
        cr.next = (state == t_state.WAIT) | reset

    return instances()

@block
def simple_fsm_implicit_else(clk, ce, reset, dout, debug):
    "case statement with implicit else and assignment from state variable to output"
    counter = Signal(modbv(0)[8:])
    state = Signal(t_state.RESET)
    cr = ResetSignal(0, 1, isasync = False)

    ctr = up_counter(clk, ce, cr, counter)

    @always_seq(clk.posedge, reset)
    def fsm():
        debug.next = 0
        if state == t_state.RESET:
            if counter == 10:
                state.next = t_state.WAIT
        elif state == t_state.RUN:
            if counter == 41:
                state.next = t_state.WAIT
        elif state == t_state.WAIT:
            debug.next = 1
            state.next = t_state.IDLE
        else:
            if counter > 20:
                state.next = t_state.RUN

    @always_comb
    def assign():
        dout.next = counter
        cr.next = (state == t_state.WAIT) | reset

    return instances()

UUT_LIST = [ complex_fsm ]

# This list should be empty when all is implemented:
UUT_LIST_FAIL = [ simple_fsm_implicit_else ]

@pytest.mark.parametrize("uut", UUT_LIST)
def test_fsm(uut):
    arst = False
    run_conversion(uut, arst, None, False) # No wrapper, no display
    run_tb(tb_unit(uut, mapped_uut, arst), 20000)

@pytest.mark.xfail
@pytest.mark.parametrize("uut", UUT_LIST_FAIL)
def test_fsm_yet_incomplete(uut):
    arst = False
    run_conversion(uut, arst, None, False) # No wrapper, no display
    run_tb(tb_unit(uut, mapped_uut, arst), 20000)



