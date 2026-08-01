# data-tooling/crawler — 多平台爬虫脚本
#
# 包含：
#   crawler_utils.py              共享工具：哈希、图片下载、记录构建、平台识别
#   crawl_public_posts.py          微信公开帖子内容抓取与脱敏
#   crawl_wechat_from_article.py   从微信文章抓取历史列表
#   sogou_wechat_crawler.py        搜狗微信搜索爬虫
#   html_structure_extractor.py    微信 BS4 HTML 提取器
#   llm_image_extractor.py         双 LLM 交叉验证图片提取
#   ollama_extractor.py            本地 Ollama 模型提取器
#   bilibili_crawler.py            B站爬虫（视频/动态/专栏 + 评论）
#   bilibili_html_extractor.py     B站 BS4 HTML 提取器
#   xiaohongshu_crawler.py         小红书爬虫（笔记 + 评论）
#   xiaohongshu_html_extractor.py  小红书 SSR JSON 提取器
#   run_full_pipeline.py           全自动流水线（wechat/bilibili/xiaohongshu）
