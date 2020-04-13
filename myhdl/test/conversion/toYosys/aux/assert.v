// Implementation of user defined assert

module user_assert(input COND);
    always @(COND)
    begin
        if (COND !== 1)
        begin
            $display("\033[7;31mASSERTION FAILED\033[0m in %m");
            $finish;
        end
    end
endmodule
