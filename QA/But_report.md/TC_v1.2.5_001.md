## Bug Report - TC_v1.2.5_001

### Environment
version : v1.2.5

### Severity
Critical

### Priority
Highest

### Reproduction Steps

1. 프로그램을 실행한다
2. 적합한 분석 예정 TXT 파일 이름을 입력한다
3. 시간 형식과 분석 키워드를 입력한다
4. 분석을 진행한다

### Expected Result

- 각 항목별 순위가 집계된다
- 기존 설정에 따라 순위 내에서 이어지는 시간대가 병합이 된다
- 각 주제별 랭크가 순위에 따라 내림차순으로 출력된다

### Actual Result

- 실질적인 순위와 상관없이 랭크가 시간 순으로 정렬되었다.
- 기대하지 않은 정렬이 되며 해당 순위와 상관없는 시간대의 순위가 병합이 되었다.

### Notes

- 코드 내에서 결과 출력시 sort() 함수가 한번 더 적용되는 현상을 확인할 수 있었다
- 결과에 해당하는 치명적인 오류이므로 확인 즉시 바로 수정을 하고 v1.2.5.1 긴급 배포를 하였다.

https://chatgpt.com/share/6a61b1ab-7e44-83ee-961a-e4ab23b67b20