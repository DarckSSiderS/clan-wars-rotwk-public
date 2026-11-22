-- Добавление локализации для заданий
-- Удаляем старую локализацию
DELETE FROM localizations WHERE identifier LIKE 'quest_%';

-- Добавляем новую локализацию
INSERT INTO localizations (identifier, ru, eng, webpage) VALUES
-- Ежедневные задания
('quest_daily_first_win', 'Первая победа дня', 'First Win of the Day', 'quests'),
('quest_daily_first_win_desc', 'Победите в 1 матче', 'Win 1 match', 'quests'),
('quest_daily_winner', 'Победитель дня', 'Daily Winner', 'quests'),
('quest_daily_winner_desc', 'Победите в 5 матчах', 'Win 5 matches', 'quests'),
('quest_daily_active_player', 'Активный игрок', 'Active Player', 'quests'),
('quest_daily_active_player_desc', 'Сыграйте 3 матча', 'Play 3 matches', 'quests'),
('quest_daily_win_streak', 'Серия побед', 'Win Streak', 'quests'),
('quest_daily_win_streak_desc', 'Победите 3 раза подряд', 'Win 3 times in a row', 'quests'),

-- Еженедельные задания
('quest_weekly_winner', 'Недельный победитель', 'Weekly Winner', 'quests'),
('quest_weekly_winner_desc', 'Победите в 10 матчах', 'Win 10 matches', 'quests'),
('quest_weekly_master', 'Мастер недели', 'Weekly Master', 'quests'),
('quest_weekly_master_desc', 'Победите в 50 матчах', 'Win 50 matches', 'quests'),
('quest_weekly_player', 'Недельный игрок', 'Weekly Player', 'quests'),
('quest_weekly_player_desc', 'Сыграйте 25 матчей', 'Play 25 matches', 'quests'),
('quest_weekly_mastery_streak', 'Серия мастерства', 'Mastery Streak', 'quests'),
('quest_weekly_mastery_streak_desc', 'Победите 10 раз подряд', 'Win 10 times in a row', 'quests'),

-- Общие тексты для заданий
('quests_title', 'Задания', 'Quests', 'quests'),
('quests_daily', 'Ежедневные', 'Daily', 'quests'),
('quests_weekly', 'Еженедельные', 'Weekly', 'quests'),
('quests_no_daily', 'Нет ежедневных заданий', 'No daily quests', 'quests'),
('quests_no_daily_description', 'Ежедневные задания появятся завтра', 'Daily quests will appear tomorrow', 'quests'),
('quests_no_weekly', 'Нет еженедельных заданий', 'No weekly quests', 'quests'),
('quests_no_weekly_description', 'Еженедельные задания появятся в следующую неделю', 'Weekly quests will appear next week', 'quests'),
('profile_tab_quests', 'Задания', 'Quests', 'quests'),
('quest_claim_reward', 'Получить награду', 'Claim Reward', 'quests'),
('quest_completed', 'Завершено', 'Completed', 'quests'),
('quest_in_progress', 'В процессе', 'In Progress', 'quests'),
('quest_expired', 'Истекло', 'Expired', 'quests'); 