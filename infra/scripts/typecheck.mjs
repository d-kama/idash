// Phase 0: bin/ と lib/ には CDK スタックコードをまだ置かない（決定事項）。
// .ts ソースが 0 件のとき tsc は TS18003（No inputs were found）で失敗するため、
// ソースが現れるまでは tsc をスキップする。スタックコード追加後は通常どおり型検査が走る。
import { readdirSync } from 'node:fs';
import { spawnSync } from 'node:child_process';

const hasTs = (dir) => {
  try {
    return readdirSync(dir).some((f) => f.endsWith('.ts'));
  } catch {
    return false;
  }
};

if (!hasTs('bin') && !hasTs('lib')) {
  console.log('infra: no .ts sources yet — skipping tsc (Phase 0).');
  process.exit(0);
}

const result = spawnSync('tsc', ['--noEmit'], { stdio: 'inherit', shell: true });
process.exit(result.status ?? 1);
