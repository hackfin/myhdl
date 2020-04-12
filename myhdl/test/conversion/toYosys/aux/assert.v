// Implementation of user defined assert

module user_assert(input COND);
    always @(COND)
    begin
        if (COND !== 1)
        begin
            $display("ASSERTION FAILED in %m");
            $finish;
        end
    end
endmodule
