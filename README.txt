贪吃蛇 3D 多人对战
==================

运行步骤：
  1. pip install websockets
  2. python3 serve.py
  3. 浏览器打开 http://localhost:20000/

文件说明：
  serve.py       服务端（HTTP + WebSocket，同端口 20000，可用环境变量 PORT 覆盖）
  index.html     前端页面
  three.min.js   Three.js 渲染库
