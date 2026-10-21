"""公開の見本: 映画の有名なシーン 10 場面（pictag の入力の形。書き出すと Krea 2 のキャプションになる）

qwen 版で見本（キャプションのある行）が足りないとき、足りない分をここから補う。テストの入力例にも使う（tests/scenes.py）。
SCENES: {画像名: {段落: 入力}}。人物の段落は、同じ名前が2つあれば A, B を付けた名前（dog A, dog B）。
action の文は三人称単数の s を省いた現在形で書いてある（Qwen に渡すときは、プロジェクトで多い方の形に直す）
"""

SCENES = {
    # タイタニック: 船首で腕を広げる
    "titanic.png": {
        "picture": "place: ship bow, open ocean, sunset\nvibes: romantic, windy\nview: from side, third-person POV",
        "action": "girl spread arms, guy hold girl's waist from behind",
        "girl": "looks: standing, eyes closed, smile\nclothes: long dress, cardigan\nbody: red/long hair",
        "guy": "looks: standing\nclothes: white shirt, suspenders\nbody: blonde/short hair",
    },
    # ローマの休日: スクーターでローマの街を走る
    "roman_holiday.png": {
        "picture": "place: Rome street, old stone buildings, sunny day\nvibes: carefree, cheerful\nview: from front, third-person POV",
        "action": "girl ride scooter, guy sit behind girl",
        "girl": "looks: sitting, smile\nclothes: white blouse, long skirt, neckerchief\nbody: black/short hair",
        "guy": "looks: sitting\nclothes: suit, tie\nbody: black/short hair",
    },
    # ラ・ラ・ランド: 夕暮れの丘でダンス（tap dance は、進行形に直すと are tapping dance になるので dance）
    "lalaland.png": {
        "picture": "place: hilltop, city lights, dusk\nvibes: romantic, dreamy\nview: from side, third-person POV",
        "action": "girl and guy dance, guy hold girl's hand",
        "girl": "looks: standing, dancing\nclothes: yellow dress\nbody: brown/long hair",
        "guy": "looks: standing, dancing\nclothes: white shirt, tie, dark pants\nbody: black/short hair",
    },
    # 雨に唄えば: 雨の街灯にぶら下がる
    "singin_rain.png": {
        "picture": "place: city street, night, heavy rain, street lamp\nvibes: joyful\nview: from front, third-person POV",
        "action": "guy hang on lamppost, guy hold closed umbrella",
        "guy": "looks: standing, smile\nclothes: suit, fedora hat\nbody: short hair",
    },
    # ティファニーで朝食を: 早朝のショーウィンドウ
    "tiffany.png": {
        "picture": "place: city street, jewelry store window, early morning\nvibes: elegant, quiet\nview: from behind, third-person POV",
        "action": "girl look at shop window, girl eat pastry",
        "girl": "looks: standing\nclothes: black dress, pearl necklace, sunglasses, long gloves\nbody: updo hair",
    },
    # 魔女の宅急便: ほうきで海辺の町の空を飛ぶ
    "kiki.png": {
        "picture": "place: sky above seaside town, red roofs\nvibes: adventurous, breezy\nview: from side, third-person POV",
        "action": "girl fly on broom, cat ride broom behind girl",
        "girl": "looks: sitting, holding broom\nclothes: dark blue dress, red hair ribbon\nbody: brown/short hair",
        "cat": "looks: sitting\nbody: black fur, big eyes",
    },
    # わんわん物語: 裏路地で1本のスパゲッティを食べる
    "lady_and_tramp.png": {
        "picture": "place: back alley, restaurant table, night\nvibes: romantic, candlelight\nview: from side, third-person POV",
        "action": "dog A and dog B eat same spaghetti strand",
        "dog A": "looks: lying\nbody: tan fur, long ears",
        "dog B": "looks: lying\nbody: gray/scruffy fur",
    },
    # シャイニング: ホテルの廊下に立つ双子
    "shining.png": {
        "picture": "place: hotel hallway, patterned carpet\nvibes: eerie, symmetrical\nview: from front, third-person POV",
        "action": "girl A and girl B stand side by side",
        "girl A": "looks: standing, staring\nclothes: light blue dress, white socks\nbody: brown/short hair",
        "girl B": "looks: standing, staring\nclothes: light blue dress, white socks\nbody: brown/short hair",
    },
    # E.T.: 満月を横切る自転車
    "et_moon.png": {
        "picture": "place: night sky, full moon, forest below\nvibes: magical\nview: from side, third-person POV\nextra: silhouette",
        "action": "boy ride bicycle across moon, alien sit in basket",
        "boy": "looks: sitting\nclothes: red hoodie\nbody: short hair",
        "alien": "looks: sitting\nbody: wrinkled brown skin, long neck",
    },
    # となりのトトロ: 雨の夜のバス停
    "totoro.png": {
        "picture": "place: rural bus stop, night, rain\nvibes: quiet, mysterious\nview: from front, third-person POV",
        "action": "girl hold umbrella, creature stand next to girl",
        "girl": "looks: standing\nclothes: skirt, rain boots\nbody: short hair",
        "creature": "looks: standing\nbody: gray fur, round belly, big ears",
    },
}
