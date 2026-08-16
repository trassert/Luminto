from pathlib import Path

ai = Path("db") / "ai" / "history.json"

# Конфиг
config = Path("configs")
db = Path("db")

# Директории и файлы в db/crocodile/
crocoall = Path("db") / "crocodile" / "all.txt"
crocomap = Path("db") / "crocodile" / "mappings.json"
crocodile = Path("db") / "crocodile" / "game.json"
pending_hints = Path("db") / "crocodile" / "pending_hints.json"

# Директория timings
mine = Path("db") / "timings" / "mine.json"

# Директория users
roles = Path("db") / "users" / "roles.json"
money = Path("db") / "users" / "money.json"
nick = Path("db") / "users" / "nicks.json"
wdraw = Path("db") / "users" / "withdraws.json"
referrals = Path("db") / "users" / "referrals.json"
crocostat = Path("db") / "users" / "crocodile_stat.json"
hellomsg = Path("db") / "users" / "hellomsg.json"
votes = Path("db") / "users" / "votes.json"
mine_stat = Path("db") / "users" / "mine.json"
topics = Path("db") / "users" / "topics.json"

# Корневые файлы в db/
items = Path("db") / "items.json"
tickets = Path("db") / "tickets.json"
mailing = Path("db") / "mailing.json"
tasks = Path("db") / "tasks.json"
data = Path("db") / "data.json"
shopc = Path("db") / "shop" / "current.json"
shop = Path("db") / "shop" / "all.json"
shopver = Path("db") / "shop" / "version.txt"

# Директория cities
cities = Path("db") / "cities" / "game.json"
chk_city = Path("db") / "cities" / "cities.txt"
bl_city = Path("db") / "cities" / "blacklist.txt"

# Директории
bot = Path("db") / "bot"
states = Path("db") / "states"
times = Path("db") / "time"
notes = Path("db") / "notes"
stats = Path("db") / "chat_stats"

log = Path("log")
shop_log = log / "shop"

old_states = Path("backup") / "states"
backup_db = Path("backup") / "db"

font = Path("fonts") / "minecraft.ttf"

chart = Path("charts") / "chart.png"

pic = Path("images")
states_pic = pic / "states"
mini_pic = pic / "minimessage"
mini_pic_bg = mini_pic / "bg.png"
