"""
Agent 入口脚本 - 交互式模式

实现 Hermes 进化工作流：检索 -> 执行 -> 反思
支持交互式循环输入任务
"""

import asyncio
from typing import Optional

from src.agent.workflow import AgentWorkflow
from src.agent.memory import SkillManager
from src.agent.llm import LLMClient
from src.utils.logger import setup_logger


logger = setup_logger("agent")


async def run(
    goal: str,
    start_url: Optional[str] = None,
    task_guidance: Optional[str] = None
) -> None:
    """
    执行任务的 Hermes 工作流
    
    工作流程：
    1. 意图检索 (Retrieval)：检索本地是否已有相关经验
    2. 执行任务 (Execution)：将任务交给 workflow 执行
    3. 自我反思与学习 (Reflection & Evolution)：提炼经验并存储
    
    Args:
        goal: 任务目标
        start_url: 起始 URL（可选）
        task_guidance: 任务指导（可选，如果提供则跳过检索阶段）
    """
    print("\n" + "=" * 80)
    print("🚀 Hermes 进化工作流启动")
    print("=" * 80)
    print(f"📋 任务目标: {goal}")
    if start_url:
        print(f"🌐 起始 URL: {start_url}")
    print("=" * 80 + "\n")
    
    # ========== 初始化核心组件 ==========
    logger.info("初始化核心组件...")
    workflow = AgentWorkflow()
    skill_manager = SkillManager()
    llm_client = LLMClient()
    
    # ========== 阶段 1：意图检索 (Retrieval) ==========
    matched_skill = None
    if task_guidance is None:
        print("🔍 【阶段 1：意图检索】")
        print("-" * 80)
        
        # 检索相关技能
        relevant_skills = skill_manager.search_skills_by_intent(
            query=goal,
            top_k=3
        )
        
        if relevant_skills:
            # 找到相关技能
            matched_skill = relevant_skills[0]  # 使用最相关的技能
            task_guidance = f"【相关经验】\n{matched_skill['guidance_sop']}"
            
            print(f"🧠 触发肌肉记忆！匹配到已有技能:")
            print(f"   📌 技能 ID: {matched_skill['skill_id']}")
            print(f"   📝 意图描述: {matched_skill['intent_description']}")
            print(f"   ✅ 成功次数: {matched_skill['success_count']}")
            print(f"   📖 指导 SOP:")
            for line in matched_skill['guidance_sop'].split('\n')[:5]:  # 只显示前 5 行
                print(f"      {line}")
            if len(matched_skill['guidance_sop'].split('\n')) > 5:
                print(f"      ...")
            logger.info(f"匹配到技能: {matched_skill['intent_description']}")
        else:
            # 未找到相关技能
            print("💭 未找到相关经验，将进行全新探索")
            logger.info("未找到相关技能，进行全新任务探索")
        
        print("-" * 80 + "\n")
    else:
        print("⚡ 跳过意图检索（已提供任务指导）\n")
    
    # ========== 阶段 2：执行任务 (Execution) ==========
    print("⚙️  【阶段 2：执行任务】")
    print("-" * 80)
    
    result = await workflow.run_task(
        goal=goal,
        start_url=start_url,
        task_guidance=task_guidance or ""
    )
    
    print("-" * 80)
    if result.success:
        print(f"✅ 任务执行成功！")
        print(f"🤖 最终结论: {result.final_thought}")
    else:
        print(f"❌ 任务执行失败")
        print(f"⚠️  错误信息: {result.error_message}")
    print(f"📊 总共耗时 {result.steps_taken} 步")
    print("-" * 80 + "\n")
    
    # ========== 阶段 3：自我反思与学习 (Reflection & Evolution) ==========
    print("🧘 【阶段 3：自我反思与学习】")
    print("-" * 80)
    
    if result.success:
        # 情况 A：全新任务探索成功（没有使用已有技能）
        if matched_skill is None:
            print("💡 检测到全新任务探索成功，进入冥想模式...")
            logger.info("开始反思提炼新技能...")
            
            try:
                # 反思提炼
                sop_text = await skill_manager.reflect_and_extract(
                    goal=goal,
                    action_history=result.actions_executed,
                    llm_client=llm_client
                )
                
                # 保存新技能（必须使用 await）
                new_skill = await skill_manager.save_new_skill(
                    goal=goal,
                    sop_text=sop_text,
                    llm_client=llm_client  # 同时加上这个，启用二次精简
                )
                
                print(f"✨ 新技能已习得并写入神经中枢！")
                print(f"   📌 技能 ID: {new_skill['skill_id']}")
                print(f"   📝 意图描述: {new_skill['intent_description']}")
                print(f"   📖 提炼的 SOP:")
                for line in sop_text.split('\n')[:10]:  # 显示前 10 行
                    print(f"      {line}")
                if len(sop_text.split('\n')) > 10:
                    print(f"      ...")
                
                logger.info(f"新技能已保存: {new_skill['skill_id']}")
                
            except Exception as e:
                print(f"⚠️  反思提炼失败: {e}")
                logger.error(f"反思提炼失败: {e}")
        
        # 情况 B：已有技能复用成功
        else:
            print(f"🎯 已有技能复用成功，增加技能权重")
            success = skill_manager.increment_success_count(matched_skill['skill_id'])
            if success:
                updated_skill = skill_manager.get_skill_by_id(matched_skill['skill_id'])
                print(f"   📌 技能 ID: {matched_skill['skill_id']}")
                print(f"   ✅ 成功次数: {matched_skill['success_count']} → {updated_skill['success_count']}")
                logger.info(f"技能权重已更新: {matched_skill['skill_id']}")
            else:
                print(f"⚠️  更新技能权重失败")
                logger.warning(f"更新技能权重失败: {matched_skill['skill_id']}")
    
    # 情况 C：任务失败
    else:
        print("💔 任务失败，不记录为技能")
        logger.info("任务失败，跳过反思阶段")
    
    print("-" * 80 + "\n")
    
    # ========== 最终总结 ==========
    print("=" * 80)
    print("🏁 Hermes 进化工作流完成")
    print("=" * 80)
    print(f"📊 执行结果: {'✅ 成功' if result.success else '❌ 失败'}")
    print(f"📊 执行步数: {result.steps_taken}")
    if matched_skill:
        print(f"🧠 使用技能: {matched_skill['intent_description']}")
    else:
        print(f"💭 全新探索: {'✨ 已习得新技能' if result.success else '未记录'}")
    print("=" * 80 + "\n")


async def main():
    """主入口函数 - 交互式模式"""
    # 初始化日志
    setup_logger()
    
    print("\n" + "=" * 80)
    print("🤖 Web Agent - 交互式模式")
    print("=" * 80)
    print("💡 输入任务目标开始执行，输入 'quit' 或 'exit' 退出")
    print("=" * 80 + "\n")
    
    while True:
        try:
            # 获取用户输入
            goal = input("📝 请输入任务目标: ").strip()
            
            # 检查退出命令
            if goal.lower() in ['quit', 'exit', 'q']:
                print("\n👋 再见！")
                break
            
            # 跳过空输入
            if not goal:
                continue
            
            # 执行任务
            start_url = "https://www.google.com"
            await run(
                goal=goal,
                start_url=start_url
            )
            
        except KeyboardInterrupt:
            print("\n\n👋 用户强制退出")
            logger.info("用户强制退出")
            break
        except EOFError:
            print("\n\n👋 输入结束，退出程序")
            break
        except Exception as e:
            print(f"\n❌ 执行出错: {e}")
            logger.error(f"执行出错: {e}", exc_info=True)
            print("\n继续等待下一个任务...\n")


if __name__ == "__main__":
    asyncio.run(main())
