"""Print per-stage measurements from k6's summary, never infer missing stages."""
import json
import sys
from pathlib import Path


def rows(path):
    data = json.loads(Path(path).read_text())['metrics']
    result = []
    for stage in (50, 100, 200, 400, 800):
        def values(name):
            return data[f'{name}{{step:{stage}}}']['values']
        latency = values('step_latency')
        errors = values('unexpected_error')['rate']
        count = values('step_requests')['count']
        assert count > 0 and 0 <= errors <= 1
        result.append((stage, count / 45, latency['med'], latency['p(95)'], latency['p(99)'], errors * 100))
    return result


if __name__ == '__main__':
    for source in sys.argv[1:]:
        print(source)
        print('| VUs | req/s | p50 ms | p95 ms | p99 ms | errors % |')
        print('|---:|---:|---:|---:|---:|---:|')
        data = rows(source)
        for stage, *numbers in data:
            print('| ' + str(stage) + ' | ' + ' | '.join(f'{value:.2f}' for value in numbers) + ' |')
        knee = next((row[0] for row in data if row[3] > 500 or row[5] > 1), None)
        print('Knee:', knee if knee else 'not reached in the measured stages')
