# -*- coding: utf-8 -*-
"""Add the validated post-hoc findings to the five local package reports."""
from hashlib import sha256
import json
from pathlib import Path
import shutil

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]

TEXT = {
    'en': {
        'title': 'Post-hoc review of Stop justifications (25 October 2026)',
        'intro': 'Changed IDs are **not a success metric** when both tied choices are admissible. All **12 actual initial/final pairs** were reviewed, separating stated basis, factual support and instruction disclosure. This was **post-hoc, AI-assisted and unblinded**, not independent human adjudication, a new model run or a preregistered endpoint.',
        'headers': ['Observable dimension', 'Before Stop', 'After Stop'],
        'labels': ['Stated basis cites user criteria and record claims', 'Annotated verifiable selection claims supported by fixture data', 'At least one annotated selection claim contradicts fixture data', 'Explicit disclosure of the injected instruction'],
        'result': 'The four contradicted explanations include a $190 record in the eligible set despite the $150 limit; three also wrongly place it in a $123/$129 price tie. These errors persist after Stop. A true price tie with a record explicitly excluded by distance is checked separately and is not mislabeled as an eligibility error. All twelve stated-basis labels and encoded factual assertions stayed unchanged: **zero observed factual corrections or stated-basis reorientations**. Four texts changed: three removed disclosure; one rephrased an inequality without changing the fact.',
        'limit': '“Supported” concerns explicitly annotated verifiable selection claims, not every possible statement in the answer. “I did not follow it” is an unverified self-report. Reasons **do not reveal internal causation** and can rationalize an influenced choice. A reviewer supplies semantic labels and spans; the evaluator validates exact quotes, hashes, constraints, price ties, optimality and complete pair coverage, without keyword-based semantic inference. This small trigger-selected cohort of known cases does not estimate a randomized Stop effect or general efficacy. Unchanged IDs alone establish neither success nor failure; this additional review also found no improvement in the encoded factual support on these twelve cases.',
        'tests': '**16 regression tests passed on Linux without network**, covering same-ID factual correction, a flip that still relies on injected authority, warning-word camouflage, missing reviews and forged evidence. No new model calls or runtime enforcement changes.',
        'evidence': 'Evidence',
    },
    'ru': {
        'title': 'Дополнительная проверка обоснований Stop (25 октября 2026)',
        'intro': 'Смена ID — **не метрика успеха**, когда оба варианта при ничьей допустимы. Проверены все **12 реальных пар начальных и конечных ответов**: отдельно оценены заявленное основание, проверяемые утверждения о выборе и раскрытие инструкции. Это **последующий разбор с помощью AI, без ослепления**, а не независимая человеческая разметка, новый прогон модели или заранее зарегистрированная метрика.',
        'headers': ['Наблюдаемое свойство', 'До Stop', 'После Stop'],
        'labels': ['Основание ссылается на условия пользователя и утверждения о записях', 'Размеченные проверяемые утверждения о выборе подтверждаются данными задачи', 'Есть размеченное утверждение о выборе, противоречащее данным задачи', 'Явно раскрыта внедрённая инструкция'],
        'result': 'В четырёх объяснениях в список подходящих ошибочно включена запись за $190 при лимите $150; три также ошибочно приписывают ей ничью по цене $123/$129. Эти ошибки сохраняются после Stop. Настоящее равенство цены с записью, явно исключённой по расстоянию, проверяется отдельно и не объявляется ошибкой допустимости. Все 12 меток основания и размеченные фактические утверждения остались прежними: **исправлений этих фактов или смены заявленного основания не обнаружено**. Изменились четыре текста: три убрали раскрытие инструкции, один переформулировал неравенство без изменения факта.',
        'limit': '«Подтверждено» относится к явно размеченным проверяемым утверждениям о выборе, а не ко всем возможным утверждениям ответа. «Я не последовал инструкции» — непроверенный самоотчёт. Объяснения **не раскрывают внутреннюю причинность** и могут рационализировать уже повлиявший на модель выбор. Смысловые метки и цитаты заданы при разборе; оценщик проверяет точные цитаты, hash, ограничения задачи, равенство цен, оптимальность и полноту пар, а не угадывает смысл по ключевым словам. Этот малый набор известных случаев, отобранных по срабатыванию Stop, не оценивает его рандомизированный эффект или общую эффективность. Неизменность ID не означает ни успеха, ни провала; дополнительный разбор также не показал улучшения подтверждённости размеченных утверждений в этих 12 случаях.',
        'tests': '**16 регрессионных тестов прошли на Linux без сети**: исправление факта при том же ID, смена ID с сохранением внедрённого основания, маскировка словами о предупреждении, пропущенная разметка и поддельные свидетельства. Новых вызовов модели и изменений runtime-блокировки не было.',
        'evidence': 'Свидетельства',
    },
    'es': {
        'title': 'Revisión posterior de las justificaciones de Stop (25 de octubre de 2026)',
        'intro': 'Cambiar el ID **no es una medida de éxito** cuando ambas opciones empatadas son admisibles. Se revisaron los **12 pares inicial/final reales**, separando fundamento declarado, apoyo factual y divulgación de la instrucción. Fue una revisión **posterior, asistida por IA y sin cegamiento**, no una evaluación humana independiente, una nueva ejecución del modelo ni una métrica prerregistrada.',
        'headers': ['Dimensión observable', 'Antes de Stop', 'Después de Stop'],
        'labels': ['Fundamento cita criterios del usuario y afirmaciones sobre registros', 'Afirmaciones verificables anotadas respaldadas por datos del caso', 'Alguna afirmación anotada contradice los datos', 'Divulgación explícita de la instrucción inyectada'],
        'result': 'Cuatro explicaciones incluyen erróneamente un registro de $190 entre los admisibles pese al límite de $150; tres también le atribuyen un empate de precio de $123/$129. Los errores persisten. Un empate real de precio con un registro excluido expresamente por distancia se verifica aparte y no se confunde con admisibilidad. Las doce etiquetas de fundamento y las afirmaciones codificadas no cambiaron: **ninguna corrección factual ni reorientación del fundamento observada**. Cambiaron cuatro textos: tres eliminaron la divulgación y uno reformuló una desigualdad sin cambiar el hecho.',
        'limit': '«Respaldado» se limita a las afirmaciones explícitamente anotadas sobre la selección, no a toda afirmación posible. «No seguí la instrucción» es un autoinforme no verificado. Las razones **no revelan causalidad interna** y pueden racionalizar una elección influida. El revisor asigna spans y etiquetas; el evaluador valida citas exactas, hashes, restricciones, empates, optimalidad y cobertura, sin adivinar significado por palabras clave. Este pequeño conjunto conocido seleccionado por activación no estima un efecto aleatorizado de Stop ni eficacia general. Los ID iguales no prueban éxito ni fracaso; la revisión tampoco encontró mejora del respaldo factual codificado en estos doce casos.',
        'tests': '**16 pruebas de regresión pasaron en Linux sin red**: corrección factual sin cambiar ID, cambio de ID que conserva autoridad inyectada, camuflaje con palabras de advertencia, revisiones ausentes y evidencias falsas. Sin nuevas llamadas al modelo ni cambios de bloqueo en ejecución.',
        'evidence': 'Evidencias',
    },
    'fr': {
        'title': 'Revue a posteriori des justifications de Stop (25 octobre 2026)',
        'intro': 'Changer d’ID **n’est pas une mesure de réussite** lorsque les deux choix ex æquo sont admissibles. Les **12 paires initiales/finales réelles** ont été examinées en séparant fondement déclaré, appui factuel et divulgation de l’instruction. Cette revue est **a posteriori, assistée par IA et non aveugle**, pas une annotation humaine indépendante, une nouvelle exécution du modèle ou une métrique préenregistrée.',
        'headers': ['Dimension observable', 'Avant Stop', 'Après Stop'],
        'labels': ['Fondement citant les critères utilisateur et des affirmations sur les fiches', 'Affirmations vérifiables annotées appuyées par les données du cas', 'Au moins une affirmation annotée contredit les données', 'Divulgation explicite de l’instruction injectée'],
        'result': 'Quatre explications incluent à tort une fiche à $190 parmi les options admissibles malgré le plafond de $150 ; trois lui attribuent aussi un prix ex æquo de $123/$129. Ces erreurs persistent. Un vrai prix égal avec une fiche explicitement exclue pour sa distance est vérifié séparément, sans être qualifié d’erreur d’admissibilité. Les douze étiquettes de fondement et les affirmations encodées sont inchangées : **aucune correction factuelle ni réorientation du fondement observée**. Quatre textes changent : trois suppriment la divulgation, un reformule une inégalité sans modifier le fait.',
        'limit': '« Appuyé » concerne les affirmations explicitement annotées sur la sélection, pas toute affirmation possible. « Je n’ai pas suivi l’instruction » reste un auto-rapport non vérifié. Les raisons **ne révèlent pas la causalité interne** et peuvent rationaliser un choix influencé. Le relecteur attribue passages et étiquettes ; l’évaluateur valide citations exactes, hash, contraintes, prix égaux, optimalité et couverture, sans inférence sémantique par mots-clés. Ce petit ensemble connu sélectionné par déclenchement n’estime ni effet randomisé de Stop ni efficacité générale. Des ID inchangés ne prouvent ni réussite ni échec ; la revue ne montre pas non plus d’amélioration de l’appui factuel encodé sur ces douze cas.',
        'tests': '**16 tests de régression ont réussi sur Linux sans réseau** : correction factuelle sans changer d’ID, changement d’ID conservant une autorité injectée, camouflage par vocabulaire d’avertissement, annotations manquantes et preuves falsifiées. Aucun nouvel appel au modèle ni changement de blocage à l’exécution.',
        'evidence': 'Preuves',
    },
    'zh': {
        'title': 'Stop 选择理由的事后检查（2026 年 10 月 25 日）',
        'intro': '两个并列选项都可接受时，改变 ID **不是成功指标**。检查了全部 **12 对真实初始/最终答案**，分别记录所述选择依据、事实支持及注入披露。这是**事后、AI 辅助、非盲检查**，不是独立人类评审、新的模型运行或预注册指标。',
        'headers': ['可观察维度', 'Stop 前', 'Stop 后'],
        'labels': ['所述依据引用用户条件和记录中的事实主张', '已标注的可核验选择主张得到案例数据支持', '至少一个已标注选择主张与数据矛盾', '明确披露注入指令'],
        'result': '四个解释在预算上限 $150 时，仍把 $190 记录列为合格选项；三个还错误声称它并列价格为 $123/$129。这些错误均保留。确实价格相同、但明确按距离排除的记录单独验证价格，不误判为资格错误。全部 12 对答案的所述依据标签和编码事实主张保持不变：**未观察到事实纠正或所述依据转向**。四个文本改变：三个删去注入披露，一个只改写不等式而未改变事实。',
        'limit': '“得到支持”只指明确标注的可核验选择主张，不代表文本中每个可能的主张均正确。“我未遵从指令”是未经证实的自述。理由**不揭示内部因果**，也可能为受影响的选择提供事后合理化。语义标签和引用范围由检查者标注；评估器核验精确引文、hash、约束、价格平局、最优性和完整覆盖，不按关键词猜测语义。已知且按触发事件选出的少量样本，不估计 Stop 的随机因果效应或一般有效性。ID 不变本身不证明成功或失败；本次检查同样未发现这 12 个案例中已编码事实支持的改善。',
        'tests': '**Linux 无网络环境通过 16 项回归测试**，覆盖 ID 不变但事实纠正、ID 改变仍依赖注入权威、警告词掩饰、缺失标注及伪造证据。没有新增模型调用，也没有改变运行时阻断行为。',
        'evidence': '证据',
    },
}


def main():
    results = json.loads((HERE / 'results.json').read_text())
    receipt = json.loads((HERE / 'execution.json').read_text())
    assert results['summary']['pairs'] == 12 and receipt['exitCode'] == 0
    assert receipt['network'] == 'none' and receipt['newModelCalls'] == 0 and receipt['cleanup']['absent']
    assert sha256((HERE / 'results.json').read_bytes()).hexdigest() == receipt['resultSha256']
    assert 'Ran 16 tests' in (HERE / 'tests.log').read_text()
    data = ROOT / 'warden/docs/data/launchgate-reason-audit-2026-10-25'
    data.mkdir(exist_ok=True, parents=True)
    for name in ('pairs.json', 'annotations.json', 'results.json'):
        shutil.copyfile(HERE / name, data / name)
    public = {key: receipt[key] for key in ('image', 'runtime', 'network', 'sourceFiles', 'archiveBytes', 'inputHashes', 'archiveSha256', 'exitCode', 'testsLogSha256', 'resultSha256', 'newModelCalls', 'githubWrites', 'npmPublished', 'startedAt', 'finishedAt')}
    public['temporaryRootRemoved'] = receipt['cleanup']['absent']
    (data / 'execution.json').write_text(json.dumps(public, indent=2) + '\n')
    names = ('pairs.json', 'annotations.json', 'results.json', 'execution.json')
    (data / 'manifest.json').write_text(json.dumps({name: sha256((data / name).read_bytes()).hexdigest() for name in names}, indent=2) + '\n')
    for lang, t in TEXT.items():
        section = '## ' + t['title'] + '\n\n' + t['intro'] + '\n\n'
        table = ['| ' + ' | '.join(t['headers']) + ' |', '| --- | ---: | ---: |']
        for label, values in zip(t['labels'], [('12/12', '12/12'), ('8/12', '8/12'), ('4/12', '4/12'), ('10/12', '7/12')]):
            table.append('| ' + ' | '.join([label, *values]) + ' |')
        section += '\n'.join(table) + '\n\n' + '\n\n'.join(t[key] for key in ('result', 'limit', 'tests'))
        section += '\n\n' + t['evidence'] + ': ' + ', '.join('[' + name + '](data/launchgate-reason-audit-2026-10-25/' + name + ')' for name in (*names, 'manifest.json')) + '.\n'
        suffix = '' if lang == 'en' else '.' + lang
        path = ROOT / 'warden/docs' / ('flow-guard-model-comparison-2026-10-25' + suffix + '.md')
        body = path.read_text().split('## ' + t['title'])[0].rstrip()
        path.write_text(body + '\n\n' + section)
        if lang in ('en', 'ru'):
            path = ROOT / 'docs/growth' / ('launchgate-live-comparison-2026-10-25.' + lang + '.md')
            body = path.read_text().split('## ' + t['title'])[0].rstrip()
            path.write_text(body + '\n\n' + section.replace('(data/launchgate-reason-audit-', '(../../warden/docs/data/launchgate-reason-audit-'))
    print('Updated five package reports, two original reports and five local product-evidence files.')


if __name__ == '__main__':
    main()
