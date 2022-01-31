-- we seem to perform a lot of counting and joining upon these columns. I'm adding two indexes:
CREATE INDEX swap_logs_tokenIn_idx ON swap_logs(tokenIn);
CREATE INDEX swap_logs_tokenOut_idx ON swap_logs(tokenOut);