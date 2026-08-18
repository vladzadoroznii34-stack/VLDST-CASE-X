import secrets
RARITIES=['COMMON','UNCOMMON','RARE','EPIC','LEGENDARY','MYTHIC']; RAW_WEIGHTS=[40,30,16,5,2.5,1.5]; WEIGHTS=[w*100/sum(RAW_WEIGHTS) for w in RAW_WEIGHTS]
def secure_rarity():
    n=secrets.randbelow(10000)/100
    s=0
    for r,w in zip(RARITIES,WEIGHTS):
        s+=w
        if n<s:return r
    return 'MYTHIC'
def level_from_xp(xp):
    lvl=1
    while lvl<100 and xp>=100*(lvl+1)*(lvl+1):lvl+=1
    return lvl
def add_xp(user,n): user.xp+=n; user.level=level_from_xp(user.xp)
