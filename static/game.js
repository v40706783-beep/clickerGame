let essence = 0.0;
let totalEarned = 0.0;
let baseClickGain = 1;
let clickMultiplier = 1.0;
let clickComboCounter = 0;
const MAX_MULTI = 3.0;
const CLICKS_PER_BOOST = 10;

const REBIRTH_BASE_COST = 5000;
const REBIRTH_COST_GROWTH = 0.75;
let rebirthCount = 0;

let passiveInterval = null;
let autoSaveInterval = null;
let saveInProgress = false;
let hasPendingSave = false;

function getRebirthCost() {
    return Math.floor(REBIRTH_BASE_COST * (1 + rebirthCount * REBIRTH_COST_GROWTH));
}

function getIncomeMultiplier() {
    // Rebirth progression: 1st x2, 2nd x3, 3rd x4, etc.
    return 1 + rebirthCount;
}

let upgrades = [
    { id: 0, name: "🌿 Травник",              desc: "+0.6 к эссенции за клик",             basePrice: 35,  type: "click_power",   level: 0, bonusPerLevel: 0.6,  currentBonus: 0 },
    { id: 1, name: "🧪 Гомункул-помощник",    desc: "Авто-варка: +0.25 эссенции/сек",       basePrice: 90,  type: "passive",       level: 0, bonusPerLevel: 0.25, currentBonus: 0 },
    { id: 2, name: "🔮 Философский камень",   desc: "Постоянный множитель клика +0.06х",    basePrice: 180, type: "click_mastery", level: 0, bonusPerLevel: 0.06, currentBonus: 0 },
    { id: 3, name: "🕯️ Эссенциальный алтарь", desc: "Ритуальный поток: +0.5 эссенции/сек", basePrice: 320, type: "passive",       level: 0, bonusPerLevel: 0.5,  currentBonus: 0 }
];

function getUpgradePrice(upgrade) {
    return Math.max(Math.floor(upgrade.basePrice * (1 + upgrade.level * 0.95)), upgrade.basePrice);
}

function recalculateBonuses() {
    let totalClickBonus = 0, totalPassive = 0, totalPermMulti = 0;
    upgrades.forEach(up => {
        if (up.type === "click_power")   totalClickBonus += up.level * up.bonusPerLevel;
        else if (up.type === "passive")  totalPassive    += up.level * up.bonusPerLevel;
        else if (up.type === "click_mastery") totalPermMulti += up.level * up.bonusPerLevel;
    });
    baseClickGain = 1 + totalClickBonus;
    window.permanentMultiBonus = totalPermMulti;
    window.basePassiveIncome = totalPassive * getIncomeMultiplier();
    updateClickMultiplierDisplay();
    updateEPSDisplay();
}

function updateClickMultiplierDisplay() {
    let heatBonus = Math.min(1.0 + (clickComboCounter / CLICKS_PER_BOOST) * 0.1, MAX_MULTI);
    clickMultiplier = heatBonus + (window.permanentMultiBonus || 0);
    document.getElementById("bonusMultiplierText").innerHTML = `x${clickMultiplier.toFixed(2)}`;
    let barPercent = ((clickComboCounter % CLICKS_PER_BOOST) / CLICKS_PER_BOOST) * 100;
    document.getElementById("heatBarFill").style.width = `${barPercent}%`;
    updateEPSDisplay();
}

function addEssence(amount) {
    essence += amount;
    if (amount > 0) totalEarned += amount;
    if (essence < 0) essence = 0;
    updateUI();
}

function handleClick() {
    if (!IS_AUTHENTICATED) {
        document.getElementById("authOverlay").style.display = "flex";
        return;
    }
    let gain = baseClickGain * clickMultiplier * getIncomeMultiplier();
    addEssence(gain);

    clickComboCounter = Math.min(clickComboCounter + 1, CLICKS_PER_BOOST * (MAX_MULTI - 1) * 10);
    updateClickMultiplierDisplay();

    const cauldron = document.getElementById("clickCauldron");
    cauldron.style.transform = "scale(0.96)";
    setTimeout(() => { if (cauldron) cauldron.style.transform = ""; }, 100);
    showFloatingText(`+${gain.toFixed(1)}`, "#ffd966");
}

function showFloatingText(text, color) {
    const div = document.createElement("div");
    div.innerText = text;
    Object.assign(div.style, {
        position: "fixed", pointerEvents: "none", fontWeight: "bold",
        fontSize: "1.4rem", color, textShadow: "0 0 3px black",
        zIndex: "999", left: "50%", top: "55%",
        transform: "translate(-50%, -50%)", opacity: "1",
        transition: "all 0.5s ease-out"
    });
    document.body.appendChild(div);
    setTimeout(() => {
        div.style.top = "40%";
        div.style.opacity = "0";
        setTimeout(() => div.remove(), 500);
    }, 20);
}

function buyUpgrade(upgrade, index) {
    let price = getUpgradePrice(upgrade);
    if (essence >= price) {
        essence -= price;
        upgrade.level++;
        recalculateBonuses();
        updateUI();
        saveGame(false);
        showFloatingText(`📜 ${upgrade.name} ур.${upgrade.level}`, "#c7f0a8");
    } else {
        showFloatingText("Не хватает эссенции!", "#ffaa88");
    }
}

function updateUI() {
    document.getElementById("essenceDisplay").innerText = Math.floor(essence * 10) / 10;
    updateEPSDisplay();

    const container = document.getElementById("upgradesList");
    container.innerHTML = "";
    upgrades.forEach((up, idx) => {
        const price = getUpgradePrice(up);
        let effectValue = up.type === "click_power"
            ? `+${up.level * up.bonusPerLevel} к клику`
            : up.type === "passive"
            ? `+${(up.level * up.bonusPerLevel).toFixed(1)}/сек`
            : `+${(up.level * up.bonusPerLevel).toFixed(1)}x множитель`;

        const card = document.createElement("div");
        card.className = "upgrade-card";
        card.innerHTML = `
            <div class="upgrade-info">
                <div class="upgrade-name">${up.name} [ур.${up.level}]</div>
                <div class="upgrade-desc">${up.desc}</div>
                <div class="upgrade-stats">✨ ${effectValue}</div>
            </div>
            <div class="upgrade-price">🧪 ${Math.floor(price)} эсс.</div>
            <button class="buy-btn" data-idx="${idx}">🍯 ВЗВАРИТЬ</button>
        `;
        container.appendChild(card);
        const btn = card.querySelector(".buy-btn");
        if (essence < price) btn.classList.add("disabled");
        btn.addEventListener("click", (e) => { e.stopPropagation(); buyUpgrade(up, idx); });
    });

    updateClickMultiplierDisplay();
    const rebirthCost = getRebirthCost();
    document.getElementById("rebirthCostText").innerText = `${Math.floor(rebirthCost)} эсс.`;
    document.getElementById("rebirthBtn").classList.toggle("disabled", essence < rebirthCost);
}

function updateEPSDisplay() {
    let eps = (window.basePassiveIncome || 0) * clickMultiplier;
    document.getElementById("epsDisplay").innerHTML = `⚗️ +${eps.toFixed(1)}/сек`;
}

function applyPassiveIncome() {
    let income = (window.basePassiveIncome || 0) * clickMultiplier;
    if (income > 0) addEssence(income);
}

async function saveGame(showToast = false) {
    if (saveInProgress) { hasPendingSave = true; return; }
    saveInProgress = true;

    const saveData = {
        essence, totalEarned, clickComboCounter,
        upgrades: upgrades.map(up => ({ level: up.level, id: up.id })),
        rebirthCount, version: 1
    };

    if (IS_AUTHENTICATED) {
        try {
            const res = await fetch("/save_game", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify(saveData)
            });
            if (!res.ok) throw new Error();
        } catch {
            showFloatingText("Ошибка сохранения!", "#ffaa88");
            saveInProgress = false;
            return;
        }
    } else {
        localStorage.setItem("alchemyClickerSave", JSON.stringify(saveData));
    }

    saveInProgress = false;
    if (hasPendingSave) { hasPendingSave = false; saveGame(false); }
    if (showToast) showFloatingText("💾 Игра сохранена!", "#b3ffcf");
}

async function loadGame() {
    let data = null;
    if (IS_AUTHENTICATED) {
        try {
            const res = await fetch("/load_game");
            if (!res.ok) return false;
            data = await res.json();
        } catch { return false; }
    } else {
        const raw = localStorage.getItem("alchemyClickerSave");
        if (!raw) return false;
        try { data = JSON.parse(raw); } catch { return false; }
    }

    essence = data.essence || 0;
    totalEarned = typeof data.totalEarned === "number" ? data.totalEarned : Math.max(0, essence);
    clickComboCounter = data.clickComboCounter || 0;
    rebirthCount = data.rebirthCount || 0;
    if (Array.isArray(data.upgrades)) {
        data.upgrades.forEach(s => {
            const t = upgrades.find(u => u.id === s.id);
            if (t) t.level = s.level;
        });
    }
    recalculateBonuses();
    updateUI();
    return true;
}

async function resetGame() {
    if (!confirm("Сбросить всю алхимическую лабораторию? Всё пропадёт!")) return;
    essence = 0; totalEarned = 0; clickComboCounter = 0; rebirthCount = 0;
    upgrades.forEach(up => up.level = 0);
    recalculateBonuses();
    updateUI();
    await saveGame(false);
    showFloatingText("🌀 Лаборатория сброшена", "#ffb347");
}

async function rebirthGame() {
    if (!IS_AUTHENTICATED) {
        document.getElementById("authOverlay").style.display = "flex";
        return;
    }
    const cost = getRebirthCost();
    if (essence < cost) { showFloatingText("Не хватает эссенции!", "#ffaa88"); return; }
    if (!confirm(`Переродиться за ${Math.floor(cost)} эсс.? Прогресс сбросится, а пассивный доход вырастет.`)) return;

    essence = 0; clickComboCounter = 0;
    upgrades.forEach(up => up.level = 0);
    rebirthCount++;
    recalculateBonuses();
    updateUI();
    await saveGame(false);
    showFloatingText(`✨ Перерождение! Множитель дохода x${getIncomeMultiplier().toFixed(2)}`, "#b3ffcf");
}

function loadLeaderboard(mode) {
    document.getElementById("lbBtnTotal").classList.toggle("lb-active", mode === "total");
    document.getElementById("lbBtnCurrent").classList.toggle("lb-active", mode === "current");
    const list = document.getElementById("lbList");
    list.innerHTML = '<div style="text-align:center;color:#cfb27c;padding:20px;">Загрузка...</div>';

    fetch(`/leaderboard?mode=${mode}`)
        .then(r => r.json())
        .then(players => {
            if (!players.length) {
                list.innerHTML = '<div style="text-align:center;color:#cfb27c;padding:20px;">Пока никого нет 🧪</div>';
                return;
            }
            const medals = ["🥇", "🥈", "🥉"];
            const rowClasses = ["lb-gold", "lb-silver", "lb-bronze"];
            list.innerHTML = players.map(p => {
                const medal = p.rank <= 3 ? medals[p.rank - 1] : `#${p.rank}`;
                const cls = p.rank <= 3 ? rowClasses[p.rank - 1] : "";
                return `<div class="lb-row ${cls}">
                    <span class="lb-rank">${medal}</span>
                    <span class="lb-name">👤 ${p.username}</span>
                    <span class="lb-value">🍯 ${p.value.toLocaleString()}</span>
                </div>`;
            }).join("");
        })
        .catch(() => {
            list.innerHTML = '<div style="text-align:center;color:#ff8888;padding:20px;">Ошибка загрузки</div>';
        });
}

async function init() {
    await loadGame();
    recalculateBonuses();
    updateUI();

    document.getElementById("clickCauldron").addEventListener("click", handleClick);
    document.getElementById("saveBtn").addEventListener("click", () => saveGame(true));
    document.getElementById("resetBtn").addEventListener("click", resetGame);
    document.getElementById("rebirthBtn").addEventListener("click", rebirthGame);
    document.getElementById("leaderboardBtn").addEventListener("click", () => {
        document.getElementById("leaderboardOverlay").style.display = "flex";
        loadLeaderboard("total");
    });

    passiveInterval = setInterval(applyPassiveIncome, 1000);
    autoSaveInterval = setInterval(() => saveGame(false), 5000);
    setInterval(updateClickMultiplierDisplay, 200);

    window.addEventListener("beforeunload", () => {
        const payload = JSON.stringify({ essence, totalEarned, clickComboCounter,
            upgrades: upgrades.map(up => ({ level: up.level, id: up.id })), rebirthCount, version: 1 });
        if (IS_AUTHENTICATED && navigator.sendBeacon) {
            navigator.sendBeacon("/save_game", new Blob([payload], { type: "application/json" }));
        } else {
            localStorage.setItem("alchemyClickerSave", payload);
        }
    });
}

init();
