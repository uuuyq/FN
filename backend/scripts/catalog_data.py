
"""常用力量训练动作库，不包含有氧及体能训练。"""

EQUIPMENT = dict(line.split('|') for line in '''barbell|杠铃
dumbbell|哑铃
bench|训练凳
pullup|单杠
rack|深蹲架
cable|绳索训练器
lat-pulldown|高位下拉机
seated-row|坐姿划船机
chest-press|推胸机
pec-deck|蝴蝶机
shoulder-press|推肩机
leg-press|腿举机
hack-squat|哈克深蹲机
leg-extension|腿屈伸机
leg-curl|腿弯举机
hip-abduction|髋外展机
hip-adduction|髋内收机
dip-bars|双杠
roman-chair|罗马椅
preacher-bench|牧师凳'''.splitlines())


# id | 中文名称 | 别名 | 主要肌群 | 器械 IDs
_ROWS = '''
# 胸部（7）
bench-press|杠铃平板卧推|Barbell Bench Press,卧推|胸大肌|barbell,bench
machine-chest|器械平板卧推|Machine Chest Press|胸大肌|chest-press
incline-db-bench|哑铃上斜卧推|Incline Dumbbell Press|胸大肌|dumbbell,bench
machine-incline-chest|器械上斜卧推|Machine Incline Chest Press|胸大肌|chest-press
machine-decline-chest|器械下斜卧推|Machine Decline Chest Press|胸大肌|chest-press
chest-dip|双杠臂屈伸（胸部侧重）|Chest Dip|胸大肌|dip-bars
pec-deck-fly|蝴蝶机夹胸|Pec Deck Fly|胸大肌|pec-deck

# 背部（8）
pull-up|引体向上|Pull Up,正握引体,对握引体,窄握引体,反握引体|背阔肌|pullup
lat-pulldown|高位下拉|Lat Pulldown,正握下拉,对握下拉,窄握下拉,反握下拉|背阔肌|lat-pulldown
single-pulldown|单臂高位下拉|Single Arm Lat Pulldown|背阔肌|lat-pulldown
machine-single-row|器械单臂划船|Single Arm Machine Row|背阔肌|seated-row
cable-row|坐姿绳索划船|Seated Cable Row|背阔肌,菱形肌|cable
t-bar-row|T杠划船|T-Bar Row|背阔肌,菱形肌|barbell
straight-pulldown|直臂绳索下压|Straight Arm Pulldown|背阔肌|cable
deadlift|传统硬拉|Deadlift|臀大肌,竖脊肌|barbell

# 肩部（7）
db-shoulder-press|哑铃肩上推举|Dumbbell Shoulder Press|三角肌前束|dumbbell
machine-shoulder|器械肩上推举|Machine Shoulder Press|三角肌前束|shoulder-press
overhead-press|站姿杠铃推举（实力推）|Overhead Press,实力推|三角肌前束|barbell
lateral-raise|哑铃侧平举|Dumbbell Lateral Raise|三角肌中束|dumbbell
cable-lateral|绳索侧平举|Cable Lateral Raise|三角肌中束|cable
reverse-pec-deck|反向蝴蝶机飞鸟|Reverse Pec Deck|三角肌后束|pec-deck
face-pull|绳索面拉|Face Pull|三角肌后束,斜方肌|cable

# 肱二头肌（6）
preacher-db-curl|牧师凳哑铃弯举|Preacher Dumbbell Curl|肱二头肌|dumbbell,preacher-bench
preacher-curl|牧师凳杠铃弯举|Preacher Barbell Curl|肱二头肌|barbell,preacher-bench
db-curl|站姿哑铃弯举|Standing Dumbbell Curl|肱二头肌|dumbbell
barbell-curl|站姿杠铃弯举|Standing Barbell Curl|肱二头肌|barbell
cable-curl|绳索弯举|Cable Curl|肱二头肌|cable
hammer-curl|哑铃锤式弯举|Hammer Curl|肱肌,肱桡肌|dumbbell

# 肱三头肌（4）
triceps-pushdown|绳索下压|Triceps Pushdown,三头下压|肱三头肌|cable
cable-overhead-extension|绳索过顶臂屈伸|Cable Overhead Triceps Extension|肱三头肌|cable
skull-crusher|杠铃仰卧臂屈伸（碎颅者）|Skull Crusher|肱三头肌|barbell,bench
triceps-dip|双杠臂屈伸（三头肌侧重）|Triceps Dip|肱三头肌|dip-bars

# 腿部（12）
squat|杠铃深蹲|Back Squat,深蹲|股四头肌,臀大肌|barbell,rack
hack-squat|哈克深蹲|Hack Squat|股四头肌|hack-squat
leg-press|器械腿举（倒蹬）|Leg Press,倒蹬|股四头肌,臀大肌|leg-press
bulgarian-split-squat|哑铃保加利亚分腿蹲|Bulgarian Split Squat|股四头肌,臀大肌|dumbbell,bench
romanian-deadlift|罗马尼亚硬拉|Romanian Deadlift,RDL|腘绳肌,臀大肌|barbell
leg-extension|腿屈伸|Leg Extension|股四头肌|leg-extension
seated-leg-curl|坐姿腿弯举|Seated Leg Curl|腘绳肌|leg-curl
lying-leg-curl|俯卧腿弯举|Lying Leg Curl|腘绳肌|leg-curl
hip-abduction|器械髋外展|Hip Abduction|臀中肌|hip-abduction
hip-adduction|器械髋内收|Hip Adduction|内收肌群|hip-adduction
hip-thrust|杠铃臀推|Barbell Hip Thrust|臀大肌|barbell,bench
back-extension|山羊挺身|Back Extension|竖脊肌,臀大肌|roman-chair

# 腹部（3）
hanging-leg-raise|悬垂举腿|Hanging Leg Raise|腹直肌,髂腰肌|pullup
cable-crunch|跪姿绳索卷腹|Kneeling Cable Crunch|腹直肌|cable
standing-cable-crunch|站姿绳索卷腹|Standing Cable Crunch|腹直肌|cable
'''

EXERCISES = []
for line in _ROWS.splitlines():
    line = line.strip()
    if line.startswith('# '):
        section = line
    if not line or line.startswith('#'):
        continue

    key, name, aliases, muscles, equipment = line.split('|')
    EXERCISES.append(dict(
        training_parts=[next(part for heading, part in [('胸部', '胸'), ('背部', '背'), ('肩部', '肩'), ('肱二头', '二头'), ('肱三头', '三头'), ('腿部', '腿'), ('腹部', '腹')] if heading in section)],
        id=key,
        name=name,
        aliases=aliases.replace(',', '、'),
        primary_muscles=muscles.replace(',', '、'),
        secondary_muscles='',
        equipment='、'.join(
            EQUIPMENT[k] for k in equipment.split(',') if k
        )
    ))
