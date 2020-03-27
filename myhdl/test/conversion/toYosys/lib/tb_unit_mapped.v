// Important: For Co-Simulation with MyHDL, use the timescale below.
// Otherwise scaling might be wrong.
`timescale 1ps/1ps

module tb_unit_mapped #(
	parameter WIDTH = 18
);

reg clk;
reg ce;
reg reset;
wire [1:0] dout;
wire debug;

initial begin
	$dumpfile("tb_unit_mapped.vcd");
    $dumpvars(0,tb_unit_mapped);

    $from_myhdl(
        clk,
        ce,
        reset
    );
    $to_myhdl(
        dout,
        debug
    );
end

uut uut_inst(
    .clk(clk),
    .dout(dout),
    .ce(ce),
    .reset(reset),
	.debug(debug)
);

endmodule
