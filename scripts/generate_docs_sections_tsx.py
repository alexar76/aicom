#!/usr/bin/env python3
"""Generate web/frontend/lib/docs-sections.tsx with full i18n via t.* references."""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "web" / "frontend" / "lib" / "docs-sections.tsx"

HEADER = r'''import React from 'react';
import {
  BookOpen,
  Zap,
  Shield,
  Bot,
  Coins,
  BarChart3,
  FileText,
  Terminal,
  Server,
  GraduationCap,
  Crown,
  Workflow,
  Palette,
  RefreshCw,
  DollarSign,
  Code2,
  Settings,
  ChevronRight,
} from 'lucide-react';
import { GlassCard } from '@/components/ui/GlassCard';
import { Badge } from '@/components/ui/Badge';
import type { DocsStrings } from '@/lib/docs-i18n/types';

export interface DocSection {
  id: string;
  title: string;
  icon: React.ElementType;
  content: React.ReactNode;
}

export type DocsSectionUi = {
  CodeBlock: React.FC<{ code: string; language?: string }>;
  InfoBox: React.FC<{ title: string; children: React.ReactNode; variant?: 'info' | 'warning' | 'success' }>;
  DocScreenshot: React.FC<{ src: string; caption: string }>;
  SubHeading: React.FC<{ children: React.ReactNode }>;
  Paragraph: React.FC<{ children: React.ReactNode }>;
  List: React.FC<{ items: React.ReactNode[] }>;
};

function endpointVariant(method: string): 'success' | 'warning' | 'info' {
  if (method === 'GET') return 'success';
  if (method === 'POST' || method === 'PATCH') return 'warning';
  return 'info';
}

function ApiCard({
  method,
  path,
  description,
  code,
  codeLanguage,
  CodeBlock,
}: {
  method: string;
  path: string;
  description: string;
  code?: string;
  codeLanguage?: string;
  CodeBlock: DocsSectionUi['CodeBlock'];
}) {
  return (
    <GlassCard className="p-4 my-3">
      <motionless className="flex items-center gap-3 mb-2">
        <Badge variant={endpointVariant(method)}>{method}</Badge>
        <code className="text-sm text-white">{path}</code>
      </motionless>
      <p className="text-sm text-gray-400">{description}</p>
      {code ? <CodeBlock code={code} language={codeLanguage} /> : null}
    </GlassCard>
  );
}

export function buildDocSections(t: DocsStrings, ui: DocsSectionUi): DocSection[] {
  const { CodeBlock, InfoBox, DocScreenshot, SubHeading, Paragraph, List } = ui;
  const st = t.sectionTitles;
  const ep = t.apiReference.endpoints;
  return [
'''

FOOTER = r'''  ];
}
'''

# Read original page for static blocks (diagrams, code)
ORIGINAL = (ROOT / "web" / "frontend" / "app" / "docs" / "page.tsx").read_text()
if "const docSections" not in ORIGINAL:
    ORIGINAL = Path("/tmp/docs-page-original.tsx").read_text()

def extract_code_block(marker: str, language: str = "bash") -> str:
    idx = ORIGINAL.find(marker)
    if idx < 0:
        return marker
    start = ORIGINAL.rfind("<CodeBlock code={`", 0, idx)
    end = ORIGINAL.find("`}", idx)
    return ORIGINAL[start + len("<CodeBlock code={`") : end]


ARCH_REWRITE = extract_code_block("next.config.js:")
DOCKER_BUILD = "docker build -t ai-factory ."
DOCKER_RUN = extract_code_block("docker run -d")
CREATE_PRODUCT = extract_code_block("# Via CLI")
CLI_INVOCATION = "docker compose exec app python /app/cli/ai_company_cli.py --help"
CLI_HIGH = extract_code_block("# First boot")
MODEL_YAML = extract_code_block("providers:")
ROUTING_YAML = extract_code_block("routing_rules:")
CONFIG_YAML = extract_code_block("# Global platform")

BODY = f"""
    {{
      id: 'overview',
      title: st.overview,
      icon: BookOpen,
      content: (
        <div>
          <h2 className="text-3xl md:text-4xl font-bold mb-4">
            <span className="text-gradient">AI-Factory v2.1</span>
          </h2>
          <Badge variant="info" className="mb-6">{{t.overview.badge}}</Badge>
          <Paragraph>
            {{t.overview.intro}}
            <strong className="text-gray-200">{{t.overview.introAutonomous}}</strong>
            {{' / '}}
            <strong className="text-gray-200">{{t.overview.introOnDemand}}</strong>
          </Paragraph>
          <SubHeading>{{t.overview.coreCapabilities}}</SubHeading>
          <List items={{t.overview.capabilities}} />
          <SubHeading>{{t.overview.atAGlance}}</SubHeading>
          <div className="grid grid-cols-2 md:grid-cols-4 gap-4 my-4">
            {{t.overview.stats.map((stat) => (
              <div key={{stat.label}} className="glass-card p-4 text-center">
                <motionless className="text-2xl font-bold text-white" dangerouslySetInnerHTML={{{{ __html: stat.value }}}} />
                <div className="text-xs text-gray-500 mt-1">{{stat.label}}</div>
              </motionless>
            ))}}
          </motionless>
          <InfoBox title={{t.overview.singleContainerTitle}} variant="info">{{t.overview.singleContainerBody}}</InfoBox>
          <InfoBox title={{t.overview.handbookTitle}} variant="success">
            {{t.overview.handbookBodyPrefix}} <code className="text-cyan-300">docs/owner-guide.md</code> {{t.overview.handbookBodySuffix}}
          </InfoBox>
          <InfoBox title={{t.overview.userGuideBoxTitle}} variant="info">
            {{t.overview.userGuideBoxPrefix}} <span className="font-medium text-gray-200">{{t.overview.userGuideBoxTab}}</span> {{t.overview.userGuideBoxSuffix}}
          </InfoBox>
        </motionless>
      ),
    }},
"""

# Fix motionless -> div in output
text = HEADER + BODY + FOOTER
text = text.replace("motionless", "motionless").replace("<motionless", "<motionless")
text = text.replace("<motionless", "<motionless")
text = text.replace("<motionless", "<motionless")
text = text.replace("<motionless", "<div")
text = text.replace("</motionless>", "</motionless>")
text = text.replace("</motionless>", "</motionless>")
text = text.replace("</motionless>", "</div>")

OUT.write_text(text)
print(f"Wrote partial {OUT} ({OUT.stat().st_size} bytes) — extend manually")
