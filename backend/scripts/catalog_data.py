"""Curated common training catalog. Sources and scope: docs/design.md."""

EQUIPMENT = dict(line.split('|') for line in '''barbell|杠铃
dumbbell|哑铃
bench|训练凳
pullup|单杠
rack|深蹲架
kettlebell|壶铃
ez-bar|曲杆杠铃
trap-bar|六角杠铃
plates|杠铃片
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
hip-thrust|臀推机
hip-abduction|髋外展机
hip-adduction|髋内收机
calf-raise|提踵机
assisted-pullup|辅助引体双杠机
dip-bars|双杠
roman-chair|罗马椅
preacher-bench|牧师凳
band|弹力带
mini-band|迷你弹力圈
trx|悬吊训练带
gym-rings|吊环
stability-ball|健身球
medicine-ball|药球
slam-ball|砸球
bosu|半球平衡球
ab-wheel|健腹轮
box|跳箱
step|踏板
rope|跳绳
battle-rope|战绳
sled|训练雪橇
sandbag|训练沙袋
treadmill|跑步机
bike|健身车
air-bike|风阻单车
rower|划船测功仪
elliptical|椭圆机
stair-climber|爬楼机
ski-erg|滑雪测功仪
mat|训练垫
foam-roller|泡沫轴'''.splitlines())

# id | Chinese name | English / Chinese aliases | primary muscles | equipment IDs
_ROWS = '''bench-press|杠铃卧推|Barbell Bench Press,卧推|胸大肌|barbell,bench
squat|杠铃深蹲|Back Squat,深蹲|股四头肌,臀大肌|barbell,rack
deadlift|硬拉|Deadlift,传统硬拉|臀大肌,竖脊肌|barbell
pull-up|引体向上|Pull Up,引体|背阔肌|pullup
push-up|俯卧撑|Push Up|胸大肌|
incline-bench|上斜杠铃卧推|Incline Barbell Bench Press|胸大肌|barbell,bench
decline-bench|下斜杠铃卧推|Decline Bench Press|胸大肌|barbell,bench
dumbbell-bench|哑铃卧推|Dumbbell Bench Press|胸大肌|dumbbell,bench
incline-db-bench|上斜哑铃卧推|Incline Dumbbell Press|胸大肌|dumbbell,bench
db-floor-press|哑铃地板卧推|Dumbbell Floor Press|胸大肌|dumbbell
db-fly|哑铃飞鸟|Dumbbell Fly|胸大肌|dumbbell,bench
incline-db-fly|上斜哑铃飞鸟|Incline Dumbbell Fly|胸大肌|dumbbell,bench
cable-fly|站姿绳索夹胸|Cable Fly,龙门架夹胸|胸大肌|cable
low-cable-fly|低位绳索夹胸|Low Cable Fly|胸大肌|cable
high-cable-fly|高位绳索夹胸|High Cable Fly|胸大肌|cable
pec-deck-fly|蝴蝶机夹胸|Pec Deck Fly|胸大肌|pec-deck
machine-chest|器械推胸|Machine Chest Press|胸大肌|chest-press
smith-bench|史密斯卧推|Smith Bench Press|胸大肌|smith,bench
kneeling-pushup|跪姿俯卧撑|Knee Push Up|胸大肌|
incline-pushup|上斜俯卧撑|Incline Push Up|胸大肌|bench
decline-pushup|下斜俯卧撑|Decline Push Up|胸大肌|bench
diamond-pushup|钻石俯卧撑|Diamond Push Up,窄距俯卧撑|肱三头肌|
dip|双杠臂屈伸|Dip|胸大肌,肱三头肌|dip-bars
assisted-dip|辅助双杠臂屈伸|Assisted Dip|胸大肌,肱三头肌|assisted-pullup
chin-up|反手引体向上|Chin Up|背阔肌,肱二头肌|pullup
neutral-pullup|对握引体向上|Neutral Grip Pull Up|背阔肌|pullup
assisted-pullup|辅助引体向上|Assisted Pull Up|背阔肌|assisted-pullup
band-pullup|弹力带辅助引体|Band Assisted Pull Up|背阔肌|pullup,band
lat-pulldown|高位下拉|Lat Pulldown|背阔肌|lat-pulldown
close-pulldown|窄握高位下拉|Close Grip Pulldown|背阔肌|lat-pulldown
reverse-pulldown|反握高位下拉|Reverse Grip Pulldown|背阔肌|lat-pulldown
straight-pulldown|直臂下拉|Straight Arm Pulldown|背阔肌|cable
barbell-row|杠铃俯身划船|Bent Over Barbell Row|背阔肌,菱形肌|barbell
pendlay-row|潘德雷划船|Pendlay Row|背阔肌,菱形肌|barbell
db-row|单臂哑铃划船|One Arm Dumbbell Row|背阔肌|dumbbell,bench
chest-supported-row|胸托哑铃划船|Chest Supported Row|背阔肌,菱形肌|dumbbell,bench
cable-row|坐姿绳索划船|Seated Cable Row|背阔肌,菱形肌|cable
machine-row|器械坐姿划船|Machine Row|背阔肌,菱形肌|seated-row
inverted-row|反向划船|Inverted Row,澳式引体|背阔肌,菱形肌|smith
trx-row|悬吊划船|TRX Row|背阔肌,菱形肌|trx
band-row|弹力带划船|Band Row|背阔肌,菱形肌|band
db-pullover|哑铃仰卧上拉|Dumbbell Pullover|背阔肌,胸大肌|dumbbell,bench
back-extension|罗马椅背伸|Back Extension,山羊挺身|竖脊肌,臀大肌|roman-chair
superman|超人式挺身|Superman|竖脊肌|
barbell-shrug|杠铃耸肩|Barbell Shrug|斜方肌|barbell
db-shrug|哑铃耸肩|Dumbbell Shrug|斜方肌|dumbbell
overhead-press|杠铃站姿推举|Overhead Press,军事推举|三角肌前束|barbell
db-shoulder-press|坐姿哑铃推肩|Seated Dumbbell Shoulder Press|三角肌前束|dumbbell,bench
arnold-press|阿诺德推举|Arnold Press|三角肌前束,三角肌中束|dumbbell,bench
machine-shoulder|器械推肩|Machine Shoulder Press|三角肌前束|shoulder-press
smith-shoulder|史密斯推肩|Smith Shoulder Press|三角肌前束|smith,bench
lateral-raise|哑铃侧平举|Dumbbell Lateral Raise|三角肌中束|dumbbell
cable-lateral|绳索侧平举|Cable Lateral Raise|三角肌中束|cable
front-raise|哑铃前平举|Dumbbell Front Raise|三角肌前束|dumbbell
rear-fly|俯身哑铃反向飞鸟|Dumbbell Reverse Fly|三角肌后束|dumbbell
reverse-pec-deck|蝴蝶机反向飞鸟|Reverse Pec Deck|三角肌后束|pec-deck
face-pull|绳索面拉|Face Pull|三角肌后束,斜方肌|cable
band-pull-apart|弹力带拉开|Band Pull Apart|三角肌后束,菱形肌|band
external-rotation|弹力带肩外旋|Band External Rotation|肩袖肌群|band
pike-pushup|折刀俯卧撑|Pike Push Up|三角肌前束|
barbell-curl|杠铃弯举|Barbell Curl|肱二头肌|barbell
ez-curl|曲杆弯举|EZ Bar Curl|肱二头肌|ez-bar
db-curl|哑铃弯举|Dumbbell Curl|肱二头肌|dumbbell
hammer-curl|锤式弯举|Hammer Curl|肱肌,肱桡肌|dumbbell
incline-curl|上斜哑铃弯举|Incline Dumbbell Curl|肱二头肌|dumbbell,bench
concentration-curl|集中弯举|Concentration Curl|肱二头肌|dumbbell,bench
preacher-curl|牧师凳弯举|Preacher Curl|肱二头肌|ez-bar,preacher-bench
cable-curl|绳索弯举|Cable Curl|肱二头肌|cable
reverse-curl|杠铃反握弯举|Reverse Curl|肱桡肌,肱肌|barbell
triceps-pushdown|绳索下压|Triceps Pushdown,三头下压|肱三头肌|cable
cable-overhead-extension|绳索过顶臂屈伸|Cable Overhead Triceps Extension|肱三头肌|cable
db-overhead-extension|哑铃过顶臂屈伸|Dumbbell Overhead Triceps Extension|肱三头肌|dumbbell
skull-crusher|仰卧曲杆臂屈伸|Skull Crusher|肱三头肌|ez-bar,bench
kickback|哑铃臂后屈伸|Triceps Kickback|肱三头肌|dumbbell
close-bench|窄握杠铃卧推|Close Grip Bench Press|肱三头肌|barbell,bench
wrist-curl|哑铃腕弯举|Wrist Curl|前臂屈肌群|dumbbell
reverse-wrist-curl|哑铃反向腕弯举|Reverse Wrist Curl|前臂伸肌群|dumbbell
front-squat|杠铃前蹲|Front Squat|股四头肌,臀大肌|barbell,rack
goblet-squat|高脚杯深蹲|Goblet Squat|股四头肌,臀大肌|kettlebell
bodyweight-squat|徒手深蹲|Bodyweight Squat|股四头肌,臀大肌|
smith-squat|史密斯深蹲|Smith Squat|股四头肌,臀大肌|smith
hack-squat|哈克深蹲|Hack Squat|股四头肌|hack-squat
leg-press|腿举|Leg Press,倒蹬|股四头肌,臀大肌|leg-press
leg-extension|坐姿腿屈伸|Leg Extension|股四头肌|leg-extension
bulgarian-split-squat|哑铃保加利亚分腿蹲|Bulgarian Split Squat|股四头肌,臀大肌|dumbbell,bench
split-squat|徒手分腿蹲|Split Squat|股四头肌,臀大肌|
forward-lunge|徒手前弓步|Forward Lunge|股四头肌,臀大肌|
reverse-lunge|哑铃后撤弓步|Reverse Dumbbell Lunge|股四头肌,臀大肌|dumbbell
walking-lunge|哑铃行走弓步|Walking Lunge|股四头肌,臀大肌|dumbbell
lateral-lunge|侧弓步|Lateral Lunge|股四头肌,内收肌群|
step-up|哑铃登阶|Dumbbell Step Up|股四头肌,臀大肌|dumbbell,box
wall-sit|靠墙静蹲|Wall Sit|股四头肌|
romanian-deadlift|杠铃罗马尼亚硬拉|Romanian Deadlift,RDL|腘绳肌,臀大肌|barbell
db-rdl|哑铃罗马尼亚硬拉|Dumbbell Romanian Deadlift|腘绳肌,臀大肌|dumbbell
single-leg-rdl|单腿哑铃硬拉|Single Leg Romanian Deadlift|腘绳肌,臀大肌|dumbbell
sumo-deadlift|相扑硬拉|Sumo Deadlift|臀大肌,股四头肌,内收肌群|barbell
trap-deadlift|六角杠硬拉|Trap Bar Deadlift|股四头肌,臀大肌|trap-bar
good-morning|杠铃早安式|Good Morning|腘绳肌,竖脊肌|barbell,rack
seated-leg-curl|坐姿腿弯举|Seated Leg Curl|腘绳肌|leg-curl
lying-leg-curl|俯卧腿弯举|Lying Leg Curl|腘绳肌|leg-curl
ball-leg-curl|健身球腿弯举|Stability Ball Leg Curl|腘绳肌|stability-ball
hip-thrust|杠铃臀推|Barbell Hip Thrust|臀大肌|barbell,bench
machine-hip-thrust|器械臀推|Machine Hip Thrust|臀大肌|hip-thrust
glute-bridge|臀桥|Glute Bridge|臀大肌|
single-glute-bridge|单腿臀桥|Single Leg Glute Bridge|臀大肌|
cable-kickback|绳索后踢腿|Cable Glute Kickback|臀大肌|cable
cable-pull-through|绳索胯下拉|Cable Pull Through|臀大肌,腘绳肌|cable
hip-abduction|坐姿髋外展|Hip Abduction|臀中肌|hip-abduction
hip-adduction|坐姿髋内收|Hip Adduction|内收肌群|hip-adduction
band-lateral-walk|弹力圈侧向走|Lateral Band Walk|臀中肌|mini-band
clamshell|蚌式开合|Clamshell|臀中肌|
standing-calf|站姿器械提踵|Standing Calf Raise|腓肠肌|calf-raise
seated-calf|坐姿器械提踵|Seated Calf Raise|比目鱼肌|calf-raise
single-calf|单腿徒手提踵|Single Leg Calf Raise|腓肠肌|
tibialis-raise|靠墙提脚尖|Tibialis Raise|胫骨前肌|
plank|平板支撑|Plank|腹横肌,腹直肌|
side-plank|侧平板支撑|Side Plank|腹斜肌|
crunch|卷腹|Crunch|腹直肌|
reverse-crunch|反向卷腹|Reverse Crunch|腹直肌|
bicycle-crunch|自行车卷腹|Bicycle Crunch|腹直肌,腹斜肌|
dead-bug|死虫式|Dead Bug|腹横肌,腹直肌|
bird-dog|鸟狗式|Bird Dog|竖脊肌,腹横肌|
hollow-hold|中空支撑|Hollow Body Hold|腹直肌|
hanging-knee-raise|悬垂举膝|Hanging Knee Raise|腹直肌,髂腰肌|pullup
hanging-leg-raise|悬垂举腿|Hanging Leg Raise|腹直肌,髂腰肌|pullup
lying-leg-raise|仰卧举腿|Lying Leg Raise|髂腰肌,腹直肌|
cable-crunch|绳索卷腹|Cable Crunch|腹直肌|cable
pallof-press|帕洛夫推举|Pallof Press,抗旋转推|腹斜肌,腹横肌|cable
woodchop|绳索伐木|Cable Woodchop|腹斜肌|cable
ab-rollout|跪姿健腹轮|Ab Wheel Rollout|腹直肌,腹横肌|ab-wheel
russian-twist|徒手俄罗斯转体|Russian Twist|腹斜肌|
farmer-carry|哑铃农夫行走|Farmer Carry|前臂屈肌群,斜方肌|dumbbell
suitcase-carry|哑铃单侧负重行走|Suitcase Carry|腹斜肌,前臂屈肌群|dumbbell
kb-swing|壶铃摆荡|Kettlebell Swing|臀大肌,腘绳肌|kettlebell
turkish-getup|土耳其起立|Turkish Get Up|三角肌,腹横肌,臀大肌|kettlebell
db-thruster|哑铃深蹲推举|Dumbbell Thruster|股四头肌,臀大肌,三角肌|dumbbell
burpee|波比跳|Burpee|股四头肌,胸大肌|
mountain-climber|登山跑|Mountain Climber|腹直肌,髂腰肌|
jumping-jack|开合跳|Jumping Jack|股四头肌,腓肠肌|
high-knees|高抬腿|High Knees|髂腰肌,股四头肌|
box-jump|跳箱|Box Jump|股四头肌,臀大肌|box
jump-squat|深蹲跳|Squat Jump|股四头肌,臀大肌|
battle-rope|战绳交替波浪|Battle Rope Waves|三角肌,腹横肌|battle-rope
sled-push|推雪橇|Sled Push|股四头肌,臀大肌|sled
slam-ball|砸球训练|Ball Slam|背阔肌,腹直肌|slam-ball
jump-rope|跳绳|Jump Rope|腓肠肌|rope
treadmill-run|跑步机跑步|Treadmill Running|股四头肌,腓肠肌|treadmill
treadmill-walk|跑步机坡度走|Incline Treadmill Walk|臀大肌,腓肠肌|treadmill
cycling|健身车骑行|Stationary Cycling|股四头肌,臀大肌|bike
air-bike|风阻单车训练|Air Bike|股四头肌,三角肌|air-bike
rowing|划船测功仪训练|Rowing Ergometer|股四头肌,背阔肌|rower
elliptical|椭圆机训练|Elliptical|股四头肌,臀大肌|elliptical
stair-climber|爬楼机训练|Stair Climber|股四头肌,臀大肌|stair-climber
ski-erg|滑雪测功仪训练|Ski Erg|背阔肌,肱三头肌|ski-erg
outdoor-run|户外跑步|Running,慢跑|股四头肌,腓肠肌|
brisk-walk|快走|Brisk Walking|股四头肌,臀大肌|'''

EXERCISES = []
for line in _ROWS.splitlines():
    key, name, aliases, muscles, equipment = line.split('|')
    EXERCISES.append(dict(id=key, name=name, aliases=aliases.split(','),
                          muscles=muscles.split(','), secondary_muscles=[],
                          equipment=[EQUIPMENT[k] for k in equipment.split(',') if k]))
