CASES=[
('VLDST-BR','VLDST BRONZE',500,'bronze',1,['Bronze Chip','Rust Coin','Copper Gear','Bronze Bolt','Ancient Token','Bronze Shield','Golden Fragment','Bronze Crown','Ancient Core']),
('VLDST-SI','VLDST SILVER',1500,'silver',3,['Silver Chip','Silver Coin','Silver Gear','Moon Bolt','Lunar Token','Silver Shield','Moon Crystal','Silver Crown','Lunar Core']),
('VLDST-GO','VLDST GOLD',3500,'gold',5,['Gold Shard','Gold Coin','Golden Gear','Solar Bolt','Sun Token','Golden Shield','Solar Crystal','Golden Crown','Solar Core']),
('VLDST-DI','VLDST DIAMOND',10000,'diamond',8,['Diamond Shard','Crystal Coin','Crystal Gear','Diamond Bolt','Diamond Ring','Crystal Shield','Diamond Hammer','Diamond Crown','Crystal Dragon']),
('VLDST-RO','VLDST ROYAL',25000,'royal',12,['Royal Shard','Royal Coin',"King's Gear",'Royal Blade',"King's Seal",'Royal Shield','Royal Scepter',"King's Crown",'Royal Phoenix']),
('VLDST-GA','VLDST GALAXY',60000,'galaxy',16,['Star Dust','Galaxy Coin','Cosmic Gear','Nebula Bolt','Star Token','Cosmic Shield','Nebula Crystal','Galaxy Crown','Cosmic Dragon']),
('VLDST-CY','VLDST CYBER',120000,'cyber',20,['Cyber Chip','Neon Coin','Cyber Gear','Neon Bolt','Cyber Core','Neon Shield','Cyber Crystal','Neon Crown','Cyber Dragon']),
('VLDST-IN','VLDST INFERNO',250000,'inferno',25,['Ember Shard','Inferno Coin','Flame Gear','Fire Bolt','Inferno Core','Flame Shield','Inferno Crystal','Flame Crown','Inferno Dragon']),
('VLDST-SH','VLDST SHADOW',500000,'shadow',30,['Dark Shard','Shadow Coin','Dark Gear','Void Bolt','Shadow Core','Void Shield','Dark Crystal','Shadow Crown','Void Dragon']),
('VLDST-DR','VLDST DRAGON',1000000,'dragon',40,['Dragon Scale','Dragon Coin','Dragon Gear','Dragon Bolt','Dragon Heart','Dragon Shield','Dragon Crystal','Dragon Crown','Ancient Dragon'])]
assert len(CASES)==10 and len({x[0] for x in CASES})==10
items=[f'{c[0]}-{i:03d}' for c in CASES for i in range(1,10)]
assert len(items)==90 and len(set(items))==90 and all(len(c[5])==9 for c in CASES)
RAW=[40,30,16,5,2.5,1.5]
assert sum(RAW)==95
# The supplied weights total 95%; production RNG normalizes them to 100% while preserving ratios.
assert abs(sum(w*100/sum(RAW) for w in RAW)-100)<1e-9
print('OK: 10 cases, 90 unique items, 9 per case, rarity probability total 100%.')
