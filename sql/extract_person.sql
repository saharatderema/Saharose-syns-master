SELECT 
    pcucodeperson,
    pid,
    cid,
    prename,
    fname,
    lname,
    sex,
    birth,
    typelive,
    dischargetype,
    d_update
FROM person
ORDER BY d_update, pcucodeperson, pid;