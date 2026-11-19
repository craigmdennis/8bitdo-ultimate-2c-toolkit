    .text
    .global cave
cave:
    tsub    sp, #40
    tmov    r5, r4
    tmov    r4, sp
    tloadrb r0, [r5, #1]
    tstorerb r0, [r4, #0]
    tstorerb r0, [r4, #1]
    tloadrb r0, [r5, #2]
    tstorerb r0, [r4, #2]
    tstorerb r0, [r4, #3]
    tloadrb r0, [r5, #3]
    tstorerb r0, [r4, #4]
    tstorerb r0, [r4, #5]
    tloadrb r0, [r5, #4]
    tstorerb r0, [r4, #6]
    tstorerb r0, [r4, #7]
    tloadrb r0, [r5, #6]
    tshftr r2, r0, #6
    tshftl r1, r0, #2
    tor r1, r2
    tstorerb r1, [r4, #8]
    tstorerb r2, [r4, #9]
    tloadrb r0, [r5, #5]
    tshftr r2, r0, #6
    tshftl r1, r0, #2
    tor r1, r2
    tstorerb r1, [r4, #10]
    tstorerb r2, [r4, #11]
    tloadrb r0, [r5, #0]
    tcmp    r0, #8
    tjmi    hat_ok
    tmovs   r0, #0
    tj      hat_store
hat_ok:
    tadd    r0, #1
hat_store:
    tstorerb r0, [r4, #12]
    tloadrb r0, [r5, #7]
    tmovs   r1, #219
    tand    r0, r1
    tstorerb r0, [r4, #13]
    tloadrb r0, [r5, #8]
    tmovs   r1, #124
    tand    r0, r1
    tstorerb r0, [r4, #14]
    tmovs   r0, #0
    tmovs   r1, #15
zero:
    tstorerb r0, [r4, r1]
    tadd    r1, #1
    tcmp    r1, #38
    tjne    zero
    tmovs   r1, #14
motion:
    tloadrb r0, [r5, r1]
    tmov    r2, r1
    tadd    r2, #8
    tstorerb r0, [r4, r2]
    tadd    r1, #1
    tcmp    r1, #26
    tjne    motion
    tloadrb r0, [r5, #9]
    tloadrb r1, [r5, #7]
    tshftr  r2, r0, #1
    tmovs   r3, #1
    tand    r2, r3
    tshftl  r0, r0, #2
    tmovs   r3, #4
    tand    r0, r3
    tor     r2, r0
    tshftr  r0, r1, #1
    tmovs   r3, #2
    tand    r0, r3
    tor     r2, r0
    tshftr  r0, r1, #2
    tmovs   r3, #8
    tand    r0, r3
    tor     r2, r0
    tstorerb r2, [r4, #16]
    tmovs   r0, #64
    tmovs   r1, #29
    tmov    r2, r4
    tmovs   r3, #38
    tjl     notify
    tadd    sp, #40
    tjl     back
