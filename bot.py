import discord
from discord.ext import commands
from discord.ui import View, Button
import json
import os
from datetime import datetime

intents = discord.Intents.default()
intents.message_content = True
intents.members = True

bot = commands.Bot(command_prefix='!', intents=intents)

# ============= КЛАССЫ ДЛЯ РАБОТЫ =============

class ApplicationSystem:
    def __init__(self):
        self.config_file = 'applications_config.json'
        self.load_config()
    
    def load_config(self):
        if os.path.exists(self.config_file):
            with open(self.config_file, 'r', encoding='utf-8') as f:
                self.config = json.load(f)
        else:
            self.config = {
                'guilds': {}
            }
            self.save_config()
    
    def save_config(self):
        with open(self.config_file, 'w', encoding='utf-8') as f:
            json.dump(self.config, f, ensure_ascii=False, indent=4)
    
    def get_guild_config(self, guild_id):
        guild_id = str(guild_id)
        if guild_id not in self.config['guilds']:
            self.config['guilds'][guild_id] = {
                'welcome_message': '📝 Заполните анкету для вступления!',
                'questions': [],
                'application_channel': None,
                'log_channel': None,
                'approved_role': None,
                'join_role': None
            }
            self.save_config()
        return self.config['guilds'][guild_id]
    
    def add_question(self, guild_id, question_text):
        guild_config = self.get_guild_config(guild_id)
        question = {
            'id': len(guild_config['questions']) + 1,
            'text': question_text,
            'required': True
        }
        guild_config['questions'].append(question)
        self.save_config()
        return question
    
    def remove_question(self, guild_id, question_id):
        guild_config = self.get_guild_config(guild_id)
        guild_config['questions'] = [q for q in guild_config['questions'] if q['id'] != question_id]
        for i, q in enumerate(guild_config['questions'], 1):
            q['id'] = i
        self.save_config()

app_system = ApplicationSystem()

# ============= КНОПКИ И МОДАЛЬНЫЕ ОКНА =============

class ApplicationView(View):
    def __init__(self):
        super().__init__(timeout=None)
    
    @discord.ui.button(label="📝 Начать анкету", style=discord.ButtonStyle.primary, custom_id="start_app")
    async def start_app(self, interaction: discord.Interaction, button: Button):
        guild_config = app_system.get_guild_config(interaction.guild_id)
        
        if not guild_config['questions']:
            await interaction.response.send_message("❌ На сервере нет вопросов!", ephemeral=True)
            return
        
        await interaction.response.send_modal(ApplicationModal(guild_config['questions']))

class ApplicationModal(discord.ui.Modal):
    def __init__(self, questions):
        super().__init__(title="📋 Анкета вступления")
        self.questions = questions
        self.answers = {}
        
        for i, question in enumerate(questions[:5]):
            text_input = discord.ui.TextInput(
                label=f"{i+1}. {question['text'][:45]}",
                placeholder="Введите ответ...",
                style=discord.TextStyle.long,
                required=True,
                max_length=500
            )
            setattr(self, f"q_{i}", text_input)
            self.add_item(text_input)
    
    async def on_submit(self, interaction: discord.Interaction):
        guild_config = app_system.get_guild_config(interaction.guild_id)
        
        # Собираем ответы
        answers = []
        for i, question in enumerate(self.questions[:5]):
            answer = getattr(self, f"q_{i}").value
            answers.append(f"**{question['text']}**\n{answer}")
        
        # Отправляем в канал
        app_channel = interaction.guild.get_channel(guild_config['application_channel'])
        if not app_channel:
            await interaction.response.send_message("❌ Канал не настроен!", ephemeral=True)
            return
        
        embed = discord.Embed(
            title="📋 Новая заявка",
            description=f"От: {interaction.user.mention}",
            color=0x3498db,
            timestamp=datetime.now()
        )
        embed.set_author(name=interaction.user.name, icon_url=interaction.user.display_avatar.url)
        
        # Объединяем ответы в одно поле (чтобы избежать лимитов)
        embed.description = f"От: {interaction.user.mention}\n\n" + "\n\n".join(answers)
        
        view = ModerationView(interaction.user.id)
        await app_channel.send(embed=embed, view=view)
        
        welcome = guild_config.get('welcome_message', '✅ Анкета отправлена!')
        await interaction.response.send_message(welcome, ephemeral=True)

class ModerationView(View):
    def __init__(self, applicant_id):
        super().__init__(timeout=None)
        self.applicant_id = applicant_id
    
    @discord.ui.button(label="✅ Принять", style=discord.ButtonStyle.green, custom_id="accept")
    async def accept(self, interaction: discord.Interaction, button: Button):
        # Сразу отвечаем, чтобы не было ошибки
        await interaction.response.send_message("⏳ Обрабатываю...", ephemeral=True)
        
        try:
            if not interaction.user.guild_permissions.administrator:
                await interaction.followup.send("❌ Недостаточно прав!", ephemeral=True)
                return
            
            guild_config = app_system.get_guild_config(interaction.guild_id)
            
            # Выдаем роль
            if guild_config.get('approved_role'):
                role = interaction.guild.get_role(guild_config['approved_role'])
                member = interaction.guild.get_member(self.applicant_id)
                
                if member and role:
                    await member.add_roles(role)
                    await interaction.followup.send(f"✅ Роль {role.name} выдана", ephemeral=True)
            
            # ЛС пользователю
            try:
                user = await bot.fetch_user(self.applicant_id)
                await user.send(f"🎉 Поздравляем! Вы приняты на сервер **{interaction.guild.name}**!")
            except:
                pass
            
            # Лог
            if guild_config.get('log_channel'):
                log = interaction.guild.get_channel(guild_config['log_channel'])
                if log:
                    await log.send(f"✅ {interaction.user.mention} принял <@{self.applicant_id}>")
            
            # Убираем кнопки
            await interaction.message.edit(view=None)
            await interaction.followup.send("✅ Готово!", ephemeral=True)
            
        except Exception as e:
            await interaction.followup.send(f"❌ Ошибка: {str(e)}", ephemeral=True)
    
    @discord.ui.button(label="❌ Отклонить", style=discord.ButtonStyle.red, custom_id="reject")
    async def reject(self, interaction: discord.Interaction, button: Button):
        await interaction.response.send_modal(RejectModal(self.applicant_id))
    
    @discord.ui.button(label="✏️ Изменения", style=discord.ButtonStyle.secondary, custom_id="changes")
    async def changes(self, interaction: discord.Interaction, button: Button):
        await interaction.response.send_modal(ChangesModal(self.applicant_id))

class RejectModal(discord.ui.Modal):
    def __init__(self, applicant_id):
        super().__init__(title="Отклонение заявки")
        self.applicant_id = applicant_id
        self.reason = discord.ui.TextInput(label="Причина", style=discord.TextStyle.long, required=True)
        self.add_item(self.reason)
    
    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        
        try:
            user = await bot.fetch_user(self.applicant_id)
            await user.send(f"❌ Заявка на сервер **{interaction.guild.name}** отклонена.\nПричина: {self.reason.value}")
            
            guild_config = app_system.get_guild_config(interaction.guild_id)
            if guild_config.get('log_channel'):
                log = interaction.guild.get_channel(guild_config['log_channel'])
                if log:
                    await log.send(f"❌ {interaction.user.mention} отклонил <@{self.applicant_id}>\nПричина: {self.reason.value}")
            
            await interaction.message.edit(view=None)
            await interaction.followup.send("✅ Заявка отклонена", ephemeral=True)
        except Exception as e:
            await interaction.followup.send(f"❌ Ошибка: {str(e)}", ephemeral=True)

class ChangesModal(discord.ui.Modal):
    def __init__(self, applicant_id):
        super().__init__(title="Запрос изменений")
        self.applicant_id = applicant_id
        self.comment = discord.ui.TextInput(label="Что исправить", style=discord.TextStyle.long, required=True)
        self.add_item(self.comment)
    
    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        
        try:
            user = await bot.fetch_user(self.applicant_id)
            await user.send(f"✏️ Заявка на сервер **{interaction.guild.name}** требует изменений:\n{self.comment.value}")
            
            guild_config = app_system.get_guild_config(interaction.guild_id)
            if guild_config.get('log_channel'):
                log = interaction.guild.get_channel(guild_config['log_channel'])
                if log:
                    await log.send(f"✏️ {interaction.user.mention} запросил изменения у <@{self.applicant_id}>")
            
            await interaction.message.edit(view=None)
            await interaction.followup.send("✅ Запрос отправлен", ephemeral=True)
        except Exception as e:
            await interaction.followup.send(f"❌ Ошибка: {str(e)}", ephemeral=True)

# ============= СОБЫТИЯ =============

@bot.event
async def on_ready():
    print(f'✅ Бот {bot.user} запущен!')
    print(f'Серверов: {len(bot.guilds)}')
    
    # Регистрируем постоянные View
    bot.add_view(ApplicationView())
    
    # Восстанавливаем кнопки модерации
    for guild in bot.guilds:
        guild_config = app_system.get_guild_config(guild.id)
        if guild_config.get('application_channel'):
            channel = guild.get_channel(guild_config['application_channel'])
            if channel:
                async for message in channel.history(limit=50):
                    if message.author == bot.user and message.components:
                        bot.add_view(ModerationView(0))

@bot.event
async def on_member_join(member):
    guild_config = app_system.get_guild_config(member.guild.id)
    if guild_config.get('join_role'):
        role = member.guild.get_role(guild_config['join_role'])
        if role:
            try:
                await member.add_roles(role)
            except:
                pass

# ============= КОМАНДЫ =============

@bot.command()
@commands.has_permissions(administrator=True)
async def setup_app(ctx):
    embed = discord.Embed(title="🔧 Настройка", color=0x00ff00)
    embed.add_field(name="!set_channel #канал", value="Канал для заявок", inline=False)
    embed.add_field(name="!set_log #канал", value="Канал для логов", inline=False)
    embed.add_field(name="!set_role @роль", value="Роль после принятия", inline=False)
    embed.add_field(name="!autorole @роль", value="Роль при входе", inline=False)
    embed.add_field(name="!add_question текст", value="Добавить вопрос", inline=False)
    embed.add_field(name="!list_questions", value="Список вопросов", inline=False)
    embed.add_field(name="!remove_question номер", value="Удалить вопрос", inline=False)
    embed.add_field(name="!post_app", value="Создать кнопку", inline=False)
    embed.add_field(name="!ping", value="Проверка бота", inline=False)
    await ctx.send(embed=embed)

@bot.command()
async def ping(ctx):
    await ctx.send("🏓 Понг!")

@bot.command()
@commands.has_permissions(administrator=True)
async def set_channel(ctx, channel: discord.TextChannel):
    app_system.get_guild_config(ctx.guild.id)['application_channel'] = channel.id
    app_system.save_config()
    await ctx.send(f"✅ Канал: {channel.mention}")

@bot.command()
@commands.has_permissions(administrator=True)
async def set_log(ctx, channel: discord.TextChannel):
    app_system.get_guild_config(ctx.guild.id)['log_channel'] = channel.id
    app_system.save_config()
    await ctx.send(f"✅ Логи: {channel.mention}")

@bot.command()
@commands.has_permissions(administrator=True)
async def set_role(ctx, role: discord.Role):
    app_system.get_guild_config(ctx.guild.id)['approved_role'] = role.id
    app_system.save_config()
    await ctx.send(f"✅ Роль: {role.mention}")

@bot.command()
@commands.has_permissions(administrator=True)
async def autorole(ctx, role: discord.Role):
    app_system.get_guild_config(ctx.guild.id)['join_role'] = role.id
    app_system.save_config()
    await ctx.send(f"✅ Роль при входе: {role.mention}")

@bot.command()
@commands.has_permissions(administrator=True)
async def set_welcome(ctx, *, text):
    app_system.get_guild_config(ctx.guild.id)['welcome_message'] = text
    app_system.save_config()
    await ctx.send(f"✅ Приветствие: {text}")

@bot.command()
@commands.has_permissions(administrator=True)
async def add_question(ctx, *, text):
    q = app_system.add_question(ctx.guild.id, text)
    await ctx.send(f"✅ Вопрос #{q['id']} добавлен")

@bot.command()
@commands.has_permissions(administrator=True)
async def list_questions(ctx):
    questions = app_system.get_guild_config(ctx.guild.id)['questions']
    if not questions:
        await ctx.send("📭 Вопросов нет")
        return
    text = "\n".join([f"{q['id']}. {q['text']}" for q in questions])
    await ctx.send(f"**Вопросы:**\n{text}")

@bot.command()
@commands.has_permissions(administrator=True)
async def remove_question(ctx, qid: int):
    app_system.remove_question(ctx.guild.id, qid)
    await ctx.send(f"✅ Вопрос {qid} удален")

@bot.command()
@commands.has_permissions(administrator=True)
async def post_app(ctx):
    embed = discord.Embed(
        title="📝 Вступление на сервер",
        description=app_system.get_guild_config(ctx.guild.id).get('welcome_message', 'Нажми кнопку ниже'),
        color=0x00ff00
    )
    await ctx.send(embed=embed, view=ApplicationView())

# ============= ЗАПУСК =============
bot.run(os.environ['TOKEN'])