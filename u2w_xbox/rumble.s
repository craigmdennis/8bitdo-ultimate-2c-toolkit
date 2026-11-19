    .text
    .global rumble
rumble:
    tloadrb r0, [r4, #12]
    tloadrb r2, [r4, #10]
    tcmp    r0, r2
    tjcs    left_max
    tmov    r0, r2
left_max:
    tloadrb r1, [r4, #13]
    tloadrb r2, [r4, #11]
    tcmp    r1, r2
    tjcs    right_max
    tmov    r1, r2
right_max:
    tloadrb r2, [r4, #16]
    tcmp    r2, #235
    tjeq    linear
    tcmp    r0, #100
    tjls    left_ok
    tmovs   r0, #100
left_ok:
    tcmp    r1, #100
    tjls    right_ok
    tmovs   r1, #100
right_ok:
    tloadr  r3, table_addr
    tloadrb r0, [r3, r0]
    tloadrb r1, [r3, r1]
    tjex    lr
linear:
    tmovs   r3, #164
    tmul    r0, r3
    tshftr  r0, r0, #6
    tcmp    r0, #255
    tjls    linear_left_ok
    tmovs   r0, #255
linear_left_ok:
    tmul    r1, r3
    tshftr  r1, r1, #6
    tcmp    r1, #255
    tjls    linear_right_ok
    tmovs   r1, #255
linear_right_ok:
    tjex    lr
    .align 2
table_addr:
    .word   table
