# -*- coding: utf-8 -*-
"""Publish nothing: save the verified factorial result in local product docs."""
from hashlib import sha256
from pathlib import Path
import json,shutil
HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[2]
TEXT={
'en':('Record references and correction directives: a four-condition model test', '''A frozen **2×2 comparison produced 384 retained fresh continuations** on Linux: twelve exact saved initial contexts × eight repetitions × four message conditions. It tests two research-adapter changes, not a released runtime modification. All model settings and initial conversations stayed fixed; `deepseek-flash`, temperature 0.3, max_tokens 700, thinking disabled. The fresh ordinal/conditional control is used for comparison, rather than the previous run’s 19/32.

| Evidence reference / request | Fully corrected explanations | False D eligibility introduced |
| --- | ---: | ---: |
| Ordinal / conditional | 22/32 | 0/32 |
| Explicit record / conditional | 25/32 | 4/32 |
| Ordinal / directive | 14/32 | 5/32 |
| Explicit record / directive | 17/32 | 14/32 |

The denominator is four known erroneous explanations × eight repetitions per condition. Full correction requires removing the original false claims **without retaining or introducing another checked contradiction**. Every selected ID remained unchanged and admissible. The eight initially supported contexts per condition (64 generations) had byte-identical review controls across labels and no observed factual regressions.

The combined treatment removed the original C-related error in **31/32**, but **14** explanations wrongly admitted D, whose distance was **2.5 km against a 1.0 km cap**. It therefore achieved only **17/32 full corrections**. In five ordinal-directive outcomes the model appended a correct C-exclusion statement while retaining the earlier false C eligibility/price claim; these are failures, not corrections. One combined-treatment answer explicitly disputed the true $190 price. These are post-hoc diagnostics, not model-internal causal explanations.

The previously zero-of-eight context yielded **1/8, 2/8, 0/8 and 1/8** in table order. Both stronger frozen predictions failed: combined ≥24/32 corrections and ≥4/8 in that context. The directional explicit-presentation prediction was positive descriptively; the directive prediction was negative. Explicit versus ordinal yielded +9.375 percentage points at either request shape; directive versus conditional yielded −25 points at either reference form. The observed interaction contrast was zero. These are descriptive counts from four cases across two fixture families, not population effects, significance claims or proof of a mechanism.

The explicit condition bundles controlled record ID, field/value and ineligibility consequence; a gain cannot be attributed to reference resolution alone. On this cohort the tested directive does not justify replacing the conditional review. No detector, grammar, prompt or WARDEN runtime was tuned from these outcomes.

## Disclosure, custody and evidence

All conditions retained model-prose disclosure in **80/80** initial-disclosure opportunities and added it in **16/16** other opportunities. The fixed compiled runtime emitted guard notices in **384/384** final replays, with no additional continuation. This is not a native-client rendering test.

**44 offline instrument/relay/collector tests** passed on factory-vps. Guard preparation and final replay ran nonroot with read-only root and no network; only the host relay called the fixed model endpoint. Keys stayed host-local. All 384 complete requests/responses were retained with zero API/format/length failures; **783 output hashes** were verified before server cleanup. Conservative accounting **$0.074455776** under the $0.12 cap; rates are assumptions, not a verified current-tariff invoice. Including the preceding separate study and its reported lost attempt, cumulative accounting is $0.181303008; outcomes are never pooled across those studies.

All **161 unique fixture/answer texts** were reviewed: 19 exact matches reused completed prior review, 142 new complete texts were read. Claims are quote/hash-bound and checked against records; treatment labels were omitted from the review index. Post-hoc AI-assisted review is not independent human/blinded adjudication. Unsupported internal rejection self-reports remain unverified. The closed grammar stayed frozen and was not used as a general semantic judge. These are development contexts, not an independent holdout. Local documents only; no npm/GitHub/blog/article/comment publication.
'''),
'ru':('Ссылки на записи и прямые команды: проверка четырёх условий', '''На Linux выполнен замороженный **эксперимент 2×2: 384 сохранённых свежих продолжения** — 12 точных прежних контекстов × 8 повторов × 4 условия. Менялись сообщения исследовательского адаптера; боевой runtime WARDEN не менялся. Модель `deepseek-flash`, temperature 0.3, max_tokens 700, thinking disabled; начальные диалоги и остальные настройки одинаковы. Контроль — свежий прогон текущего сообщения, а не прежние 19/32.

| Ссылка на факт / просьба | Полностью исправлены объяснения | Ошибочно допущен D |
| --- | ---: | ---: |
| Номер записи / условная | 22/32 | 0/32 |
| Явная запись / условная | 25/32 | 4/32 |
| Номер записи / прямая команда | 14/32 | 5/32 |
| Явная запись / прямая команда | 17/32 | 14/32 |

Знаменатель — четыре известных ошибочных объяснения × восемь повторов на условие. Полное исправление требует убрать исходную ошибку **без сохранения или добавления другого проверяемого противоречия**. Все выбранные ID остались прежними и допустимыми. На восьми исходно подтверждённых контекстах (64 генерации на условие) сообщения всех четырёх меток побайтово одинаковы, новых фактических регрессий не обнаружено.

Сочетание изменений убрало исходную ошибку про C в **31/32** случаях, но **14** ответов ошибочно включили D: расстояние до него **2,5 км при лимите 1 км**. Поэтому полных исправлений только **17/32**. В пяти ответах с номером и прямой командой модель добавила верную фразу об исключении C, сохранив прежнее неверное утверждение о допустимости/цене C. Это не исправления. Один ответ совместного условия прямо отрицал верную цену $190. Эти диагностические разрезы последующие и не устанавливают внутренний механизм модели.

Прежний случай 0/8 дал **1/8, 2/8, 0/8 и 1/8** по порядку таблицы. Оба сильных заранее заданных прогноза не выполнены: совместное условие ≥24/32 и ≥4/8 на этом случае. Направленный прогноз для явной записи описательно подтвердился, для прямой команды — нет. Явная запись дала +9,375 процентного пункта при обеих формах просьбы; прямая команда дала −25 пунктов при обеих формах ссылки. Наблюдаемое взаимодействие равно нулю. Это описательные результаты четырёх случаев из двух семейств, не оценка общего эффекта и не доказательство причинного механизма.

Явное представление одновременно уточняет контролируемый ID записи, поле/значение и следствие недопустимости; нельзя приписать прирост одному сопоставлению ID. Проверенная прямая команда не даёт основания заменять ею условную перепроверку. По этим результатам детектор, грамматика, модельные инструкции и runtime не подстраивались.

## Раскрытие, исполнение и свидетельства

Во всех условиях раскрытие в тексте модели удержано **80/80** раз и добавлено в **16/16** остальных возможностей. Замороженный runtime выдал уведомления guard в **384/384** конечных повторах без дополнительного продолжения. Отображение в нативном клиенте не проверялось.

На factory-vps прошли **44 офлайн-теста инструментов, relay и сборщика**. Подготовка guard и конечный replay — nonroot, read-only root, без сети; только host relay вызывал фиксированный API. Ключи оставались серверными. Сохранены все 384 полных запроса/ответа; ошибок API/формата/длины нет. **783 хеша** проверены до удаления серверного каталога. Учётная оценка **$0,074455776** при cap $0,12; это расчёт по принятым ставкам, не проверенный счёт актуального тарифа. Вместе с предыдущим отдельным исследованием и его потерянной попыткой учётная сумма $0,181303008; результаты исследований не объединяются.

Оценены **161 уникальный текст**: 19 точных совпадений используют завершённый прежний разбор, прочитаны 142 новых полных объяснения. Утверждения привязаны к цитатам/хешам и проверены по данным; метки условий скрыты в индексе текстов. Последующая AI-assisted разметка не является независимой человеческой или ослеплённой оценкой. Заявления модели о собственном непринятии инструкции не доказываются. Закрытая грамматика заморожена и не выдаётся за универсальную семантическую проверку. Независимого holdout нет. Документы локальные; npm/GitHub/блог/статья/комментарий не публиковались.
'''),
'es':('Referencias y órdenes de corrección: comparación de cuatro condiciones', '''**384 continuaciones nuevas conservadas en Linux**, con plan 2×2 congelado: 12 contextos iniciales exactos × 8 repeticiones × 4 mensajes. Cambios en el adaptador de investigación, no en el runtime publicado. `deepseek-flash`, temperatura 0.3, máximo 700 tokens, thinking desactivado. Se usa el control nuevo de esta ejecución, no el anterior 19/32.

| Referencia / petición | Correcciones completas | D declarado admisible por error |
| --- | ---: | ---: |
| Ordinal / condicional | 22/32 | 0/32 |
| Registro explícito / condicional | 25/32 | 4/32 |
| Ordinal / orden directa | 14/32 | 5/32 |
| Registro explícito / orden directa | 17/32 | 14/32 |

Cuatro errores conocidos × ocho repeticiones por condición. Una corrección completa no puede conservar ni introducir otra contradicción verificable. Todos los ID quedaron iguales y admisibles. Sin nuevas contradicciones en los 64 controles inicialmente apoyados por condición; sus mensajes son idénticos entre tratamientos.

La combinación retiró el error original de C en **31/32**, pero 14 respuestas admitieron D a **2.5 km con límite de 1 km**: sólo **17/32** correcciones completas. Cinco respuestas ordinal/directa añadieron una exclusión correcta de C sin borrar su afirmación falsa anterior; no pasan. Una respuesta conjunta negó explícitamente el precio verdadero de $190. Son diagnósticos posteriores, no mecanismos internos demostrados.

El antiguo caso 0/8 dio **1/8, 2/8, 0/8, 1/8**. Fallaron ambas predicciones fuertes previas: conjunto ≥24/32 y ese caso ≥4/8. Presentación explícita: +9.375 puntos a cada forma de petición; orden directa: −25 puntos a cada referencia. Interacción observada cero. Cuatro casos de dos familias, sin inferencia poblacional ni significación general. La referencia explícita combina ID, campo/valor y consecuencia; no aísla sólo resolver ID. Estos datos no justifican sustituir la revisión condicional por la orden probada. Runtime, gramática y prompts no se ajustaron con los resultados.

## Divulgación y ejecución

Cada condición retuvo divulgación **80/80** y la añadió **16/16**. El guard emitió avisos **384/384**, sin otra continuación; presentación nativa sin medir. Pasaron **44 pruebas offline** de instrumentos/relay/colección. Guard y pruebas sin red; sólo relay anfitrión con API, clave en servidor. 384 solicitudes/respuestas completas, cero errores; **783 hash** verificados antes de limpiar. Contabilidad conservadora **$0.074455776**, cap $0.12; no factura actual verificada. Total con el estudio previo separado y su intento perdido: $0.181303008, sin combinar resultados.

Revisión de **161 textos únicos**: 19 coincidencias exactas con revisión anterior, 142 textos nuevos completos leídos. Citas/hash y hechos verificados; etiquetas omitidas del índice. Revisión posterior con IA, no humana independiente/ciega; ninguna causalidad interna inferida. Gramática congelada, sin validación semántica universal ni holdout independiente. Sólo documentos locales, ninguna publicación npm/GitHub/blog/artículo/comentario.
'''),
'fr':('Références et consignes de correction : quatre conditions', '''Plan 2×2 gelé : **384 nouvelles continuations conservées sur Linux**, 12 contextes initiaux exacts × 8 répétitions × 4 messages. Adaptateur de recherche modifié, pas le runtime publié. `deepseek-flash`, température 0.3, maximum 700 tokens, thinking désactivé. Comparaison au nouveau contrôle de cette exécution, pas aux anciens 19/32.

| Référence / demande | Corrections complètes | D admis à tort |
| --- | ---: | ---: |
| Ordinal / conditionnelle | 22/32 | 0/32 |
| Fiche explicite / conditionnelle | 25/32 | 4/32 |
| Ordinal / consigne directe | 14/32 | 5/32 |
| Fiche explicite / consigne directe | 17/32 | 14/32 |

Quatre erreurs connues × huit répétitions par condition. Une correction complète ne conserve ni n’introduit d’autre contradiction vérifiable. Tous les ID restent identiques et admissibles. Aucune nouvelle contradiction sur les 64 contrôles initialement appuyés par condition ; leurs messages sont identiques entre traitements.

La combinaison retire l’erreur C dans **31/32**, mais 14 réponses admettent D à **2.5 km pour une limite de 1 km** : seulement **17/32** corrections complètes. Cinq réponses ordinal/directe ajoutent l’exclusion correcte de C tout en gardant la fausse affirmation antérieure ; elles échouent. Une réponse conjointe nie explicitement le vrai prix $190. Diagnostics a posteriori, pas de mécanisme interne établi.

L’ancien cas 0/8 donne **1/8, 2/8, 0/8, 1/8**. Les deux prédictions fortes échouent : combinaison ≥24/32 et ce cas ≥4/8. Présentation explicite : +9.375 points pour chaque demande ; consigne directe : −25 points pour chaque référence. Interaction observée nulle. Quatre cas de deux familles, sans effet populationnel ou significativité générale revendiqués. La référence explicite combine ID, champ/valeur et conséquence ; elle n’isole pas la résolution d’ID. Remplacer la revue conditionnelle par cette consigne n’est pas justifié ici. Aucun ajustement du runtime, de la grammaire ou des prompts à partir des résultats.

## Divulgation et exécution

Chaque condition conserve la divulgation **80/80** et l’ajoute **16/16**. Avis du guard **384/384**, aucune continuation supplémentaire ; rendu natif non testé. **44 tests offline** d’instrument/relay/collecte réussis. Guard/tests sans réseau ; seul relay hôte avec API, clé sur serveur. 384 requêtes/réponses complètes, aucune erreur ; **783 hash** vérifiés avant nettoyage. Comptabilité prudente **$0.074455776**, plafond $0.12, pas une facture actuelle vérifiée. Total avec l’étude précédente séparée et son essai perdu : $0.181303008, sans regrouper les résultats.

**161 textes uniques** évalués : 19 correspondances exactes réutilisent la revue précédente, 142 nouveaux textes complets lus. Citations/hash et faits contrôlés, labels omis de l’index. Revue a posteriori assistée par IA, pas humaine indépendante/aveugle ; causalité interne inconnue. Grammaire gelée, pas de validation sémantique universelle ni de holdout indépendant. Documents locaux uniquement, aucune publication npm/GitHub/blog/article/commentaire.
'''),
'zh':('记录引用与纠错命令：四条件模型测试', '''冻结的 2×2 设计在 Linux 保留 **384 次新继续生成**：12 个精确初始上下文 × 8 次重复 × 4 种消息。只改变研究适配器消息，不修改发布的 runtime。`deepseek-flash`，temperature 0.3，最大 700 tokens，thinking 关闭。对照来自本轮，不把上一轮 19/32 当成本轮对照。

| 引用 / 请求 | 完整纠正 | 错误认定 D 合格 |
| --- | ---: | ---: |
| 序号 / 条件式 | 22/32 | 0/32 |
| 明确记录 / 条件式 | 25/32 | 4/32 |
| 序号 / 直接命令 | 14/32 | 5/32 |
| 明确记录 / 直接命令 | 17/32 | 14/32 |

每条件分母为 4 个已知错误 × 8 次。完整纠正不能保留或引入其他可核验矛盾。所有选中 ID 均不变且合格。每条件 64 个初始有支持的控制上下文未见新增矛盾，四种标签下消息完全相同。

组合条件在 **31/32** 中去除了 C 的原错误，但 14 个解释又认定 D 合格，而 D 距离 **2.5 公里、上限为 1 公里**，因此完整纠正仅 **17/32**。5 个序号/命令回答追加了正确的 C 排除句，却保留先前错误主张，仍算失败。一个组合回答明确否认真实 $190 价格。这些是事后诊断，不证明内部机制。

原 0/8 案例本轮依次为 **1/8、2/8、0/8、1/8**。组合 ≥24/32 以及该案例 ≥4/8 两项强预测均失败。明确呈现两层请求下均 +9.375 个百分点；直接命令两种引用下均 −25 点，观察到的交互差为零。仅两类上下文的 4 个案例，不推断总体或一般显著性。明确呈现同时改变 ID、字段/值与不合格后果，不能只归因于 ID 解析。本轮不支持用该命令替换条件式复查。未根据结果调整 runtime、语法或模型提示。

## 披露与执行

每条件保留披露 **80/80**，新增披露 **16/16**。Guard 提示 **384/384**，无额外继续生成；原生显示未测。**44 项工具/relay/收集离线测试**通过。Guard/测试无网络，只有宿主 relay 调用 API，密钥留在服务器。保留 384 次完整请求/响应，无错误；删除前核验 **783 个哈希**。保守核算 **$0.074455776**，上限 $0.12，不是已验证当前账单。与此前单独研究及其丢失尝试合计 $0.181303008，但不合并结果。

核查 **161 个唯一文本**：19 个精确匹配复用此前审查，完整阅读 142 个新文本。引用/哈希和事实可核验，索引省略处理标签。事后 AI 辅助审查，不是独立人类/盲法裁定；内部因果未知。语法冻结，不是普遍语义验证或独立留出集。仅本地文档，未发布 npm、GitHub、博客、文章或评论。
''')}

def main():
 a=json.loads((HERE/'analysis.json').read_text());arms=['ordinal_conditional','explicit_conditional','ordinal_directive','explicit_directive'];assert [a['treatments'][x]['factual_corrections'] for x in arms]==[22,25,14,17]
 data=ROOT/'warden/docs/data/launchgate-review-factors-2026-10-26';data.mkdir(parents=True,exist_ok=True)
 names=['analysis.json','artifact-audit.json','review-decisions.json','review-index.json','scored-pairs.json','annotations.json','reason-audit.json','protocol.md','custody.md']
 for name in names:shutil.copyfile(HERE/name,data/name)
 (data/'manifest.json').write_text(json.dumps({name:sha256((data/name).read_bytes()).hexdigest() for name in names},indent=2)+'\n')
 nav=' · '.join('['+lang+'](flow-guard-review-factors-2026-10-26'+('' if lang=='en' else '.'+lang)+'.md)' for lang in TEXT)
 table=['| Initial case | Ordinal/conditional | Explicit/conditional | Ordinal/directive | Explicit/directive |','| --- | ---: | ---: | ---: | ---: |']
 cases=sorted(a['treatments'][arms[0]]['by_initial_error'],key=lambda r:(r['fixture'],r['original_repeat']))
 for case in cases:
  table.append('| '+case['fixture']+' / original '+str(case['original_repeat'])+' | '+' | '.join(str(next(x for x in a['treatments'][arm]['by_initial_error'] if x['source_pair_id']==case['source_pair_id'])['corrected'])+'/8' for arm in arms)+' |')
 for lang,(title,body) in TEXT.items():
  suffix='' if lang=='en' else '.'+lang
  labels={'en':['Initial case','Ordinal/conditional','Explicit/conditional','Ordinal/directive','Explicit/directive'],'ru':['Исходный случай','Номер / условная','Запись / условная','Номер / команда','Запись / команда'],'es':['Caso inicial','Ordinal/condicional','Explícito/condicional','Ordinal/directo','Explícito/directo'],'fr':['Cas initial','Ordinal/conditionnel','Explicite/conditionnel','Ordinal/direct','Explicite/direct'],'zh':['初始案例','序号/条件式','明确/条件式','序号/命令','明确/命令']}
  localized_table=table.copy();localized_table[0]='| '+' | '.join(labels[lang])+' |'
  links=', '.join('['+name+'](data/launchgate-review-factors-2026-10-26/'+name+')' for name in ['analysis.json','artifact-audit.json','scored-pairs.json','annotations.json','protocol.md','manifest.json'])
  p=ROOT/'warden/docs'/('flow-guard-review-factors-2026-10-26'+suffix+'.md');p.write_text('# '+title+'\n\n'+nav+'\n\n'+body+'\n'+'\n'.join(localized_table)+'\n\n'+links+'.\n')
  for prefix in ['flow-guard-constraint-evidence','flow-guard-fresh-rechecks-2026-10-26']:
   p=ROOT/'warden/docs'/(prefix+suffix+'.md');s=p.read_text().split('<!-- factorial-review-followup -->')[0].rstrip()
   p.write_text(s+'\n\n<!-- factorial-review-followup -->\n\n['+title+'](flow-guard-review-factors-2026-10-26'+suffix+'.md).\n')
 p=ROOT/'docs/growth/launchgate-review-factors-2026-10-26.ru.md';p.write_text('# '+TEXT['ru'][0]+'\n\n'+TEXT['ru'][1]+'\n'+'\n'.join(['| Исходный случай | Номер / условная | Запись / условная | Номер / команда | Запись / команда |',*table[1:]])+'\n\n[Документация на пяти языках и данные](../../warden/docs/flow-guard-review-factors-2026-10-26.ru.md). [Протокол, архивы и свидетельства](../evidence/launchgate-review-factors-2026-10-26/README.md).\n')
 print('Saved five local product reports, evidence manifest and Russian growth report.')
if __name__=='__main__':main()
