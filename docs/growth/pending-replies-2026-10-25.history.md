# Historical queue snapshots

Superseded: use pending-replies-2026-10-25.ru.md. Do not repost these historical drafts.

# Обращения читателей: состояние и подготовленные ответы

**Текущий порядок, 25 октября:** новые комментарии готовим здесь чистым текстом, пользователь вставляет их сам. Новые письма открываем в Outlook без отправки. До новых публикаций сначала готовим необходимые письма; Vulnetix по последнему поручению остаётся в ожидании. Исторические записи об отправках и публикациях ниже не являются разрешением повторять их.

**Актуализация:** пользователь сообщил, что jkming уже ответил сам. У статей Martin, Kartik и Raju метка Fully Autonomous снята; у jkming оставлена. Для новых ответов активная вкладка Chrome не требуется: тексты выдаём пользователю. Micky проверен на Linux; новые замечания Launch Gate и Kevin об аннотациях разбираются отдельно от прежнего вопроса Kevin о биллинге.

**Обновление 25 октября, 10:47 МСК:** статьи по [когорте 292](https://dev.to/alexar76/we-rechecked-292-failing-mcp-packages-12-newer-releases-now-list-tools-p72), [вопросу jkming](https://dev.to/alexar76/we-kept-wardens-810-thresholds-and-fixed-its-credential-index-4khn) и [пяти плательщикам Martin](https://dev.to/alexar76/five-wallets-paid-an-x402-seller-what-can-we-say-about-demand-5gek) опубликованы от alexar76 с Fully Autonomous. Окончательные ответы со ссылками: [jkming](publication-2026-10-25/jkming/reply.md), [Martin](publication-2026-10-25/martin/Reply.md), [Kartik](publication-2026-10-25/kartik/reply.md). Комментарии пока не отправлены; Martin/jkming ждут активной авторизованной DEV-вкладки Chrome. [Все языковые версии и статусы](publication-2026-10-25/README.md).

Срез 25 октября 2026, 07:09 МСК: 54 статьи DEV, 87 комментариев. После предыдущего среза появились
одно первое техническое обращение и один новый запрос в существующей ветке. Ответы ниже — черновики;
они не опубликованы и не отправлены. SWARM уже получил письмо и публичное подтверждение контакта.

## jkming — короткие фрагменты секретов

[Вопрос, 06:03 МСК](https://dev.to/alexar76/we-attacked-our-own-mcp-firewall-with-its-source-code-open-14-of-17-attacks-got-through-now-2-of-2m7l#comment-3ion2).
Спрашивает, можно ли опустить порог для не-hex ниже восьми символов, чтобы ловить шестисимвольные
фрагменты внутри других слов, и что происходит с коллизиями. Это первое обращение, ответа пока нет.

Проверено по текущему локальному коду: сильные окна — 8 символов, для hex-only значений 10.
Отдельный механизм коротких изолированных фрагментов 5–7 символов запрашивает review; два разных
соседних шестисимвольных фрагмента одного прочитанного credential могут дать сильное совпадение.
Фрагмент внутри более длинного непрерывного слова не становится изолированным atom. Наличие этой
ветки в локальном коде само по себе не подтверждает её публикацию в конкретном npm-релизе.

Основания: [сильные окна](https://github.com/alexar76/warden/blob/main/src/flow-guard-fingerprints.ts),
[короткие фрагменты](https://github.com/alexar76/warden/blob/main/src/flow-guard-fragments.ts),
[сохранённое измерение коллизий](https://github.com/alexar76/warden/blob/main/scripts/redteam/results/window-collisions.json).

Подготовленный ответ:

> Thanks — this prompted a 6/7/8 comparison through the actual hooks, in networkless Linux containers.
> I’m keeping 8 for non-hex and 10 for hex. Six produced false hard denials in 31 deliberately selected
> public-text collision cases; seven reproduced a known false denial on ordinary JSON/health-check
> text, even though it had no exact hits in the new 22-million-character corpus. Those controls are
> counterexamples, not a production false-positive rate.
>
> A lone six-character piece inside a longer word still isn’t reliably identified as a secret. In the
> current local source, the separate credential boundary asks before supported outbound/MCP calls
> after a credential read and outside text. All 14,400 attack calls stopped at ask or deny at every
> threshold; that is not a claim that the substring detector caught them all.
>
> I also fixed an indexing gap: it skipped payload letters before a key’s first digit. Restricting the
> change to recognized normalized provider prefixes converted 717 attack decisions from ask to deny,
> with unchanged decisions on 7,680 public-request fixtures. The strict default still asks on all
> those benign calls; exact reviewed public rules let them pass once. The fix is local and unreleased,
> and it does not turn six-character substrings into reliable strong matches.
>
> Disclosure: I maintain WARDEN. AI assisted the experiment code, analysis and drafting of this reply.

Выполнено по поручению пользователя: [серверное сравнение 6/7/8, ограничения и исправление](warden-thresholds-2026-10-25.ru.md).
Все 29 760 входов на вариант сверены попарно по SHA-256; сильные пороги 8/10 сохранены. Код,
копия плагина и регрессии готовы локально; 1 156 тестов и typecheck прошли. Ответ не опубликован.
Статья уже опубликована; окончательный ответ со ссылкой и явным раскрытием создания AI-агентами
находится в пакете публикации выше. Он заменяет приведённый здесь предварительный текст.

## Martin / textokit — признаки sweeper-плательщиков

[Продолжение, 01:20 МСК](https://dev.to/alexar76/we-tried-to-buy-one-call-from-100-x402-sellers-most-delivered-almost-nobody-is-buying-2498#comment-3ioef).
Сообщает, что его единственный повторный плательщик повторяет опубликованный inputExample, и
выражает готовность использовать признаки sweeper-подобного поведения для классификации receipts.
Предыдущие сообщения получили ответы; это новый запрос, а не давно оставленное первое обращение.

Это заявленный интерес к конкретной функции. Внешний запуск такой функции и покупка продукта
этим сообщением ещё не подтверждены. Разбор кошельков в нашем предыдущем ответе и tool-list diff
HISTOR — разные источники результата. На первоначальном срезе функции разметки ещё не было;
ниже добавлены результаты её локальной реализации и проверки по поручению пользователя.

Подготовленный ответ:

> Thanks, Martin. I checked all five payers against a fixed fourteen-day Base USDC window. All 24
> external payments in your current ledger match successful transfers for the stated amounts:
> 0.055 USDC in total, including our own 0.001 USDC research probe.
>
> For 0x7722… I found 1,010 recipients, 90.0% paid once, with 83.3% of transfers at or below 0.01 USDC.
> For 0xA1d1… it was 1,632 recipients, 86.8% paid once, and 76.4% at or below 0.01 USDC. Those exact
> fractions are more useful than my earlier “nearly all” wording. Recipients are addresses, not
> necessarily merchants or x402 services.
>
> I also implemented a local, unreleased `histor payer-audit` command that exports the counts,
> settlement references, observation window and sourced indications. Your inputExample observation
> is explicitly marked as publisher-reported; I have not independently checked request payloads.
> The strict automatic rule leaves uncertain cases as unknown and retains the full settled amount.
> None of that establishes buyer intent, and paid monitoring can still be genuine use.
>
> Disclosure: I maintain HISTOR and AIMarket; this reply was drafted with AI assistance.

Выполнено локально по поручению пользователя: [английский отчёт](textokit-five-payers-2026-10-25.md),
[русское пояснение](textokit-five-payers-2026-10-25.ru.md), [функция и инструкция](https://github.com/alexar76/histor/blob/main/docs/payer-audit.md).
Все 24 внешних платежа проверены; 605 диапазонов сети прочитаны без пропусков. Код ещё не выпущен
и не развёрнут. Сверка с известными Martin мониторами остаётся способом проверить назначения, но
для подготовленного отчёта дополнительные закрытые данные не требуются. Ответ не опубликован.

## Очередь после этих обращений

1. Kartik: статья по когорте 292 опубликована, продолжение ответа подготовлено. Поимённая публичная таблица без private-host полей готова локально; CSV наружу пока не выгружался.
2. Для Raju опубликован [полный CI-пример](https://dev.to/alexar76/a-copyable-mcp-tool-cost-check-for-ci-with-passing-and-failing-examples-3hl5) со скриптом и passing/failing-командами. Продолжение ответа подготовлено, не отправлено; внешний запуск его командой пока не подтверждён.
3. Предложить Auten и Jakub/KyttoMCP короткие проверки их конкретных сценариев.
4. Согласовать публичные карточки и описание расписания с каноническими версиями; локальные изменения и публикацию учитывать отдельно.

Свидетельства проверки веток: [последний review](../evidence/unanswered-comments-2026-10-25/refresh/review.json).

## Чек-лист: готовность ответов и недостающие данные

Статусы публичных веток — по проверке 25 октября в 07:09 МСК, не новая онлайн-проверка.
Первые два пункта — новые обращения без ответа на том срезе. Остальные — продолжения уже
отвеченных веток и работа с полученными результатами. Все действия ниже остаются локальными;
черновики jkming и Martin не опубликованы.

1. **jkming:** [серверный эксперимент 6/7/8](warden-thresholds-2026-10-25.ru.md) завершён,
   исправление индекса реализовано локально; пороги 8/10 сохранены. Ответ с результатами и
   раскрытием AI обновлён выше, не опубликован. Новых данных для этого ответа не требуется;
   нулевая production-частота ошибок и надёжное распознавание любой части из шести символов не заявляются.
2. **Martin/textokit:** ответ с раскрытием AI обновлён выше. [Отчёт по пяти плательщикам](textokit-five-payers-2026-10-25.md)
   и `histor payer-audit` реализованы локально; settlement и полное 14-дневное окно проверены.
   Для этих результатов новых данных не требуется. Его пометки известных мониторов помогут
   проверить назначения кошельков; закрытые payloads и credentials не нужны. Ответ не опубликован.
3. **[Kartik](https://dev.to/alexar76/we-installed-12915-mcp-servers-and-started-each-one-41-never-answered-3heh#comment-3i31k):**
   [исследовательский отчёт по 292 пакетам](mcp-sdk-recovery-2026-10-24.ru.md) и
   [поимённая таблица](../evidence/mcp-sdk-recovery-2026-10-24/packages.csv) готовы.
   [Публичная статья](https://dev.to/alexar76/we-rechecked-292-failing-mcp-packages-12-newer-releases-now-list-tools-p72) опубликована,
   [продолжение ответа](publication-2026-10-25/kartik/reply.md) с поправкой старой категории SDK готово,
   но не отправлено. Два случая с авторизацией/индексом честно остаются непроверенными; новых прогонов для ответа не требуется.
4. **[Raju](https://dev.to/alexar76/what-an-mcp-servers-tool-list-costs-we-counted-the-tokens-of-34374-of-them-3011#comment-3ij29):**
   [Самодостаточный CI-пример](https://dev.to/alexar76/a-copyable-mcp-tool-cost-check-for-ci-with-passing-and-failing-examples-3hl5)
   опубликован от alexar76: полный скрипт, pinned-версии, exit 0 и намеренный exit 1, шаги CI.
   HTTP 200 и доступ без авторизации проверены. Метка Fully Autonomous с этой статьи снята;
   нового ответа в исходной ветке не отправляли. Для внешнего кейса нужны лог запуска его командой
   и повтор после следующего изменения; публикация инструкции ещё не подтверждает внешнее внедрение.
5. **[Arhan](https://dev.to/alexar76/45-of-remote-mcp-servers-changed-their-tool-definitions-in-four-weeks-the-log-is-now-a-dataset-2mhe#comment-3iekp):**
   [разрез по исходным 2 036 серверам готов](arhan-change-breakdown-2026-10-25.ru.md):
   1 994 имели правки описаний сверх цифр/пробелов, 39 — только числовые в этой части, 3 — только пробельные.
   Разобраны все 7 319 событий; отдельно 5 482 изменения верхних descriptions (5 014 / 462 / 6).
   Полные состояния и digest проверены на Linux, схемы и состав tools посчитаны с пересечениями;
   12 событий без полных состояний остаются unknown. [Ответ с раскрытием AI](arhan-reply-2026-10-25.en.md)
   подготовлен, не отправлен. Новых замеров для этого ответа не требуется; числовые правки не названы безопасными.
6. **[Auten](https://dev.to/alexar76/we-re-ran-our-mcp-scanner-comparison-on-14933-npm-and-pypi-tool-lists-in-gvisor-with-two-more-21i4#comment-3i5ai):**
   [подготовка выполнена](auten-launcher-check-2026-10-25.ru.md): найден реальный sandbox baseline
   `@autenai/mcp@0.1.5` с `install_auten`; свежие npm/registry/HISTOR данные сверены.
   [Сборщик полных снимков](https://github.com/alexar76/warden/blob/main/examples/launcher-evidence/README.md) готов и прошёл 10 тестов на Linux
   с опубликованным WARDEN 0.21.0. [Запрос автору](auten-launcher-request-2026-10-25.en.md) подготовлен,
   не отправлен. Второй настоящий снимок и точная версия/артефакт его runner ещё нужны от Auten;
   реальные внешние окружения и использование команды не считаются нами воспроизведёнными.
7. **[Jakub/KyttoMCP](https://dev.to/alexar76/mcp-servers-edit-the-instructions-your-agent-reads-warden-018-shows-which-words-changed-397f#comment-3ikoh):**
   [конкретный diff и проверка готовы](jakub-review-check-2026-10-25.ru.md): `@mapled/mcp` 0.21.5 → 0.21.6,
   33 tools, два изменённых описания, новая фраза `carry on without asking`. Полные изменённые описания
   сверены с npm-архивами. Published WARDEN 0.21.0 выделяет фразу, но ошибочно советует pin из
   self-reported версии 0.1.0. Это и потеря serverInfo в пути wrap исправлены локально; 142 теста
   и 19 проверок replay прошли на Linux. [Чистый текст ответа](jakub-reply-2026-10-25.en.md) готов,
   не отправлен; пользователь вставляет комментарии сам. Исправление ещё не выпущено, human usability не измерялась.
8. **[Pushpendra](https://dev.to/alexar76/a-flow-guard-for-mcp-what-agentdojo-measured-and-what-our-security-audit-found-2ckm#comment-3i73h):**
   для доли человеческих подтверждений нужны реальные события запросов и решений approve/deny
   с общим знаменателем. Сейчас human approval остаётся unknown; количество задач с запросом
   подтверждения не заменяет эту метрику.
9. **[Kevin Hall](https://dev.to/alexar76/we-installed-12915-mcp-servers-and-started-each-one-41-never-answered-3heh#comment-3hmmh):**
   [контролируемый тест готов](kevin-fake-billing-2026-10-25.ru.md): 26 сценариев × 3 повтора на Linux,
   отдельный журнал фиктивного биллинга. Текущий canary выбирает preview без списания, `{}` включает
   серверный purchase и списывает 7 mock credits. Одинаковые MCP-сообщения могут соответствовать
   разным списаниям; ошибка и таймаут не доказывают отсутствие эффекта. WARDEN с default policy
   не угадывает платность; настроенное подтверждение sensitive tool проверено отдельно.
   [Текст ответа](kevin-reply-2026-10-25.en.md) подготовлен, не отправлен. Исходная распространённость
   и поведение Apify этим синтетическим тестом не установлены; реальных платежей не было.
10. **[Micky Arun](https://dev.to/alexar76/one-key-for-an-agents-tool-calls-a-prepaid-usdc-balance-on-an-mcp-connection-a06#comment-3h1m7):**
    [проверка текущего платёжного цикла завершена](micky-payment-lifecycle-2026-10-25.ru.md):
    146 тестов и trace из 14 шагов прошли на Linux с фиктивными средствами. Проверены reserve,
    capture/release, ошибки, гонки и expiry. Зафиксированы ограничения: нет output-metered overage
    и per-key dollar/hour cap; retry после таймаута может повторить внешний эффект; release
    возвращает service credits, а не USDC. [Чистый ответ](micky-reply-2026-10-25.en.md) готов,
    не отправлен. Production и реальные платежи не проверялись; платёжный код не менялся.
11. **[Vulnetix](https://github.com/Vulnetix/advisory-database/issues/5#issuecomment-6385911773):**
    [поправки статьи](../malware-feed-accuracy.ru.md) на пяти языках готовы локально. Для завершения
    всей истории не хватает отдельных решений по helios-broadcast, skopos-fleet и aimarket-histor;
    для заявления о проверенных исправлениях — независимой повторной проверки пяти уязвимостей.
    По поручению пользователя **ждём**; перед любой публикацией сначала нужны письма.
12. **SWARM:** первое письмо уже отправлено 20 октября, публичное подтверждение контакта тоже есть.
    Дубликат не нужен. Перед дальнейшим продолжением проверить новые входящие; прежний поиск
    без ответа не устанавливает состояние почты на текущий момент.
13. **[Launch Gate](https://dev.to/alexar76/we-attacked-our-own-mcp-firewall-with-its-source-code-open-14-of-17-attacks-got-through-now-2-of-2m7l#comment-3ipii):**
    [проверка методологии и сохранённых ответов](launchgate-methodology-2026-10-25.ru.md) выполнена.
    Официальные 18/20 сохраняются: predicate проверяет упоминание названия, а не рекомендацию.
    Два из 20 сохранённых текстов упираются в прежний предел 2 000 символов; полные 0/20 adoption
    не установлены. Захват будущих ответов исправлен локально. [Ответ](launchgate-reply-2026-10-25.en.md)
    готовится для ручной вставки; upstream issue и правки опубликованной статьи наружу не отправляются.
14. **[Kevin Hall — аннотации и подмена ответа](https://dev.to/alexar76/we-attacked-our-own-mcp-firewall-with-its-source-code-open-14-of-17-attacks-got-through-now-2-of-2m7l#comment-3ipg1):**
    [отдельное новое замечание проверено](kevin-annotations-answer-review-2026-10-25.ru.md).
    Локально добавлен opt-in review аннотаций перед первым использованием;
    server claims не дают разрешения. Исправлен обход повторной проверки ответа через слова о warning.
    Семантическая подмена выбора строк остаётся ограничением; повторная проверка не доказывает
    правильность ответа. Целевой набор **268/268** прошёл на Linux; найденная при прогоне ошибка
    защиты конфигурации с `HOME=/` тоже исправлена. [Чистый ответ](kevin-annotations-reply-2026-10-25.en.md)
    подготовлен; после дополнительного исправления двух гонок ожидания подтверждения финальная
    проверка ещё идёт. Изменения остаются локальными и не выпущены.
