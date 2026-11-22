// Сравнение счёта «Угадай ход мастера» за партию целиком с уровнем мастеров (таск 14.3).
// Мастер в каждом отобранном моменте играл лучший ход, то есть набрал бы максимум; сравниваем долю очков игрока
// от этого максимума и называем уровень по порогам. Чистые правила без сети: ничего не хранится, считает клиент.

/** Уровень результата; ключ каталога — `guess.level.<id>` (en/uk/ru). */
export type GuessLevelId = 'master' | 'near' | 'confident' | 'learning';

/** Нижние границы доли очков (в процентах) по убыванию: первая подошедшая задаёт уровень. */
export const GUESS_LEVEL_THRESHOLDS: ReadonlyArray<{ id: GuessLevelId; minPercent: number }> = [
    {id: 'master', minPercent: 90},
    {id: 'near', minPercent: 70},
    {id: 'confident', minPercent: 40},
    {id: 'learning', minPercent: 0},
];

export interface GuessLevel {
    /** Доля очков игрока от максимума, целых процентов (0 при пустой партии). */
    percent: number;
    id: GuessLevelId;
}

/** Уровень по набранным очкам и максимуму (100 за момент); пустая партия считается нулевой. */
export function guessLevel(points: number, max: number): GuessLevel {
    const percent = max > 0 ? Math.max(0, Math.min(100, Math.round((points / max) * 100))) : 0;
    const tier = GUESS_LEVEL_THRESHOLDS.find((item) => percent >= item.minPercent)!;
    return {percent, id: tier.id};
}
