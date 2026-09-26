# Parlay construction experiment

## 1X2 de-margin method

| de-margin    |   market w |   train LL |   test LL | fav (p>=60%) pred/actual   | longshot (p<25%) pred/actual   |
|:-------------|-----------:|-----------:|----------:|:---------------------------|:-------------------------------|
| proportional |        0.9 |     0.998  |    1.0046 | 68.5% / 72.0% (n=1405)     | 19.5% / 17.9% (n=6626)         |
| proportional |        1   |     0.9978 |    1.0044 | 68.6% / 72.0% (n=1423)     | 19.4% / 17.8% (n=6637)         |
| power        |        0.9 |     0.9975 |    1.0037 | 69.5% / 71.4% (n=1688)     | 19.1% / 18.8% (n=7416)         |
| power        |        1   |     0.9974 |    1.0036 | 69.8% / 71.3% (n=1729)     | 19.0% / 18.9% (n=7505)         |

## Strategies (3 parlays per run window, odds 2.70-3.50, real opening Avg odds)

| strategy                                      | split   |   parlays |   avg_legs |   avg_odds | p_prop   | p_cal   | hit   | roi    |
|:----------------------------------------------|:--------|----------:|-----------:|-----------:|:---------|:--------|:------|:-------|
| A: max probability (current), prop. de-margin | train   |       943 |       3.01 |       2.73 | 31.0%    | 31.5%   | 32.9% | -10.2% |
| A: max probability (current), prop. de-margin | test    |       464 |       2.96 |       2.73 | 29.6%    | 30.3%   | 27.8% | -24.0% |
| B: max expected return, power de-margin       | train   |      1812 |       2    |       2.99 | 30.3%    | 31.5%   | 32.5% | -3.6%  |
| B: max expected return, power de-margin       | test    |      1040 |       2    |       2.94 | 29.8%    | 31.2%   | 29.7% | -12.7% |
| C: max expected return, legs p>=55%           | train   |      1672 |       2.5  |       2.84 | 30.7%    | 32.2%   | 30.7% | -12.9% |
| C: max expected return, legs p>=55%           | test    |       950 |       2.67 |       2.86 | 28.9%    | 31.0%   | 29.8% | -15.1% |
| D: max expected return, any 2-4 legs          | train   |      1812 |       2    |       2.99 | 30.3%    | 31.5%   | 32.5% | -3.6%  |
| D: max expected return, any 2-4 legs          | test    |      1040 |       2    |       2.94 | 29.8%    | 31.2%   | 29.7% | -12.7% |
| E: max probability, 2 legs only               | train   |       395 |       2    |       2.76 | 32.3%    | 32.5%   | 33.4% | -7.7%  |
| E: max probability, 2 legs only               | test    |       197 |       2    |       2.76 | 31.4%    | 31.7%   | 27.4% | -24.4% |
| F: max expected return, 2 legs only           | train   |      1805 |       2    |       2.99 | 30.3%    | 31.5%   | 32.5% | -3.5%  |
| F: max expected return, 2 legs only           | test    |      1035 |       2    |       2.94 | 29.8%    | 31.2%   | 29.8% | -12.6% |

Leg mix on test seasons:

- A: max probability (current), prop. de-margin: {'12': 0.43, '1X': 0.16, 'X2': 0.12, 'Over 2.5': 0.09, 'Home': 0.08, 'Under 2.5': 0.08}
- B: max expected return, power de-margin: {'Home': 0.69, 'Away': 0.22, 'Under 2.5': 0.05, 'Over 2.5': 0.04, '12': 0.01, '1X': 0.0}
- C: max expected return, legs p>=55%: {'Home': 0.43, 'Under 2.5': 0.18, 'Over 2.5': 0.15, 'Away': 0.14, '12': 0.07, '1X': 0.02}
- D: max expected return, any 2-4 legs: {'Home': 0.69, 'Away': 0.22, 'Under 2.5': 0.05, 'Over 2.5': 0.04, '12': 0.01, '1X': 0.0}
- E: max probability, 2 legs only: {'Under 2.5': 0.25, 'Over 2.5': 0.22, 'Home': 0.14, 'X2': 0.12, '1X': 0.12, '12': 0.09}
- F: max expected return, 2 legs only: {'Home': 0.69, 'Away': 0.22, 'Under 2.5': 0.05, 'Over 2.5': 0.04, '12': 0.01, '1X': 0.0}