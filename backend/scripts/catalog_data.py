
"""常用力量训练动作库，不包含有氧及体能训练。"""

EQUIPMENT = dict(line.split('|') for line in '''barbell|杠铃
dumbbell|哑铃
bench|训练凳
pullup|单杠
rack|深蹲架
kettlebell|壶铃
ez-bar|曲杆杠铃
smith|史密斯机
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
calf-raise|提踵机
assisted-pullup|辅助引体双杠机
dip-bars|双杠
roman-chair|罗马椅
preacher-bench|牧师凳
ab-wheel|健腹轮'''.splitlines())


# id | 中文名称 | 别名 | 主要肌群 | 器械 IDs
_ROWS = '''
# 胸部（12）
bench-press|杠铃卧推|Barbell Bench Press,卧推|胸大肌|barbell,bench
incline-bench|上斜杠铃卧推|Incline Barbell Bench Press|胸大肌|barbell,bench
dumbbell-bench|哑铃卧推|Dumbbell Bench Press|胸大肌|dumbbell,bench
incline-db-bench|上斜哑铃卧推|Incline Dumbbell Press|胸大肌|dumbbell,bench
cable-fly|站姿绳索夹胸|Cable Fly,龙门架夹胸|胸大肌|cable
pec-deck-fly|蝴蝶机夹胸|Pec Deck Fly|胸大肌|pec-deck
machine-chest|器械推胸|Machine Chest Press|胸大肌|chest-press
smith-bench|史密斯卧推|Smith Bench Press|胸大肌|smith,bench
push-up|俯卧撑|Push Up|胸大肌|
dip|双杠臂屈伸|Dip|胸大肌,肱三头肌|dip-bars
assisted-dip|辅助双杠臂屈伸|Assisted Dip|胸大肌,肱三头肌|assisted-pullup

# 背部（12）
pull-up|引体向上|Pull Up,引体|背阔肌|pullup
assisted-pullup|辅助引体向上|Assisted Pull Up|背阔肌|assisted-pullup
chin-up|反手引体向上|Chin Up|背阔肌,肱二头肌|pullup
lat-pulldown|高位下拉|Lat Pulldown|背阔肌|lat-pulldown
close-pulldown|窄握高位下拉|Close Grip Pulldown|背阔肌|lat-pulldown
straight-pulldown|直臂下拉|Straight Arm Pulldown|背阔肌|cable
barbell-row|杠铃俯身划船|Bent Over Barbell Row|背阔肌,菱形肌|barbell
db-row|单臂哑铃划船|One Arm Dumbbell Row|背阔肌|dumbbell,bench
chest-supported-row|胸托哑铃划船|Chest Supported Row|背阔肌,菱形肌|dumbbell,bench
cable-row|坐姿绳索划船|Seated Cable Row|背阔肌,菱形肌|cable
machine-row|器械坐姿划船|Machine Row|背阔肌,菱形肌|seated-row
back-extension|罗马椅背伸|Back Extension,山羊挺身|竖脊肌,臀大肌|roman-chair

# 肩部（9）
overhead-press|杠铃站姿推举|Overhead Press,军事推举|三角肌前束|barbell
db-shoulder-press|坐姿哑铃推肩|Seated Dumbbell Shoulder Press|三角肌前束|dumbbell,bench
machine-shoulder|器械推肩|Machine Shoulder Press|三角肌前束|shoulder-press
lateral-raise|哑铃侧平举|Dumbbell Lateral Raise|三角肌中束|dumbbell
cable-lateral|绳索侧平举|Cable Lateral Raise|三角肌中束|cable
rear-fly|俯身哑铃反向飞鸟|Dumbbell Reverse Fly|三角肌后束|dumbbell
reverse-pec-deck|蝴蝶机反向飞鸟|Reverse Pec Deck|三角肌后束|pec-deck
face-pull|绳索面拉|Face Pull|三角肌后束,斜方肌|cable

# 手臂（12）
barbell-curl|杠铃弯举|Barbell Curl|肱二头肌|barbell
ez-curl|曲杆弯举|EZ Bar Curl|肱二头肌|ez-bar
db-curl|哑铃弯举|Dumbbell Curl|肱二头肌|dumbbell
hammer-curl|锤式弯举|Hammer Curl|肱肌,肱桡肌|dumbbell
incline-curl|上斜哑铃弯举|Incline Dumbbell Curl|肱二头肌|dumbbell,bench
preacher-curl|牧师凳弯举|Preacher Curl|肱二头肌|ez-bar,preacher-bench
cable-curl|绳索弯举|Cable Curl|肱二头肌|cable
triceps-pushdown|绳索下压|Triceps Pushdown,三头下压|肱三头肌|cable
cable-overhead-extension|绳索过顶臂屈伸|Cable Overhead Triceps Extension|肱三头肌|cable
db-overhead-extension|哑铃过顶臂屈伸|Dumbbell Overhead Triceps Extension|肱三头肌|dumbbell
skull-crusher|仰卧曲杆臂屈伸|Skull Crusher|肱三头肌|ez-bar,bench
close-bench|窄握杠铃卧推|Close Grip Bench Press|肱三头肌|barbell,bench

# 腿部 / 臀部（21）
squat|杠铃深蹲|Back Squat,深蹲|股四头肌,臀大肌|barbell,rack
front-squat|杠铃前蹲|Front Squat|股四头肌,臀大肌|barbell,rack
goblet-squat|高脚杯深蹲|Goblet Squat|股四头肌,臀大肌|kettlebell
smith-squat|史密斯深蹲|Smith Squat|股四头肌,臀大肌|smith
hack-squat|哈克深蹲|Hack Squat|股四头肌|hack-squat
leg-press|腿举|Leg Press,倒蹬|股四头肌,臀大肌|leg-press
leg-extension|坐姿腿屈伸|Leg Extension|股四头肌|leg-extension
bulgarian-split-squat|哑铃保加利亚分腿蹲|Bulgarian Split Squat|股四头肌,臀大肌|dumbbell,bench
reverse-lunge|哑铃后撤弓步|Reverse Dumbbell Lunge|股四头肌,臀大肌|dumbbell
deadlift|硬拉|Deadlift,传统硬拉|臀大肌,竖脊肌|barbell
romanian-deadlift|杠铃罗马尼亚硬拉|Romanian Deadlift,RDL|腘绳肌,臀大肌|barbell
db-rdl|哑铃罗马尼亚硬拉|Dumbbell Romanian Deadlift|腘绳肌,臀大肌|dumbbell
seated-leg-curl|坐姿腿弯举|Seated Leg Curl|腘绳肌|leg-curl
lying-leg-curl|俯卧腿弯举|Lying Leg Curl|腘绳肌|leg-curl
hip-thrust|杠铃臀推|Barbell Hip Thrust|臀大肌|barbell,bench
glute-bridge|臀桥|Glute Bridge|臀大肌|
cable-kickback|绳索后踢腿|Cable Glute Kickback|臀大肌|cable
hip-abduction|坐姿髋外展|Hip Abduction|臀中肌|hip-abduction
hip-adduction|坐姿髋内收|Hip Adduction|内收肌群|hip-adduction
standing-calf|站姿器械提踵|Standing Calf Raise|腓肠肌|calf-raise
seated-calf|坐姿器械提踵|Seated Calf Raise|比目鱼肌|calf-raise

# 核心（9）
plank|平板支撑|Plank|腹横肌,腹直肌|
side-plank|侧平板支撑|Side Plank|腹斜肌|
crunch|卷腹|Crunch|腹直肌|
reverse-crunch|反向卷腹|Reverse Crunch|腹直肌|
hanging-knee-raise|悬垂举膝|Hanging Knee Raise|腹直肌,髂腰肌|pullup
hanging-leg-raise|悬垂举腿|Hanging Leg Raise|腹直肌,髂腰肌|pullup
cable-crunch|绳索卷腹|Cable Crunch|腹直肌|cable
ab-rollout|跪姿健腹轮|Ab Wheel Rollout|腹直肌,腹横肌|ab-wheel
russian-twist|徒手俄罗斯转体|Russian Twist|腹斜肌|
'''

EXERCISES = []
for line in _ROWS.splitlines():
    line = line.strip()
    if not line or line.startswith('#'):
        continue

    key, name, aliases, muscles, equipment = line.split('|')
    EXERCISES.append(dict(
        id=key,
        name=name,
        aliases=aliases.replace(',', '、'),
        primary_muscles=muscles.replace(',', '、'),
        secondary_muscles='',
        equipment='、'.join(
            EQUIPMENT[k] for k in equipment.split(',') if k
        )
    ))
