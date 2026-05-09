import asyncio
from src.agent.workflow.workflow import AgentWorkflow
from src.utils.logger import setup_logger

logger = setup_logger("main")

async def main():
    agent = AgentWorkflow()
    
    # 任务目标
    my_goal = "在当前页面填写商品信息并发布。"
    
    # 动态注入的业务 Skill (SOP)
    my_skill = """
    【商品自动上架 SOP】:
    1. 第一步：必须先使用 `read_file` 动作读取本地文件 `tests/merchant/product_info.json`。
    2. 第二步：拿到返回的 JSON 结果后，结合网页截图的红框，分步执行 `type` 和 `select_option` 填写表单（如商品标题、价格、库存等）。
    3. 第三步：遇到图片上传区域，使用 `upload_file` 动作上传对应的图片。
    4. 第四步：所有必填项填写完毕后，点击【发布】按钮。
    """
    
    logger.info("🚀 开始执行本地上架测试...")
    result = await agent.run_task(
        goal=my_goal,
        start_url="http://localhost:8765/",
        task_guidance=my_skill
    )
    
    if result.success:
        logger.info("🎉 任务圆满完成！")
    else:
        logger.error(f"❌ 任务失败: {result.error_message}")

if __name__ == "__main__":
    asyncio.run(main())