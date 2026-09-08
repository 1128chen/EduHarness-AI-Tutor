##LeetCode Hot100 刷题训练营种子数据。
##课程化：章节=知识点(带先修形成学习路径)；每题=自写题面(仅用题号做课程编排引用，
##不复制 LeetCode 官方题干/示例，避免版权问题)；每章一篇知识点文档、每题一篇详细题解文档。
##另生成 3 名学员的合成作答轨迹，保证"今日复习队列/驾驶舱"当天就有内容。
##用法:
##    python -m eduharness.scripts.seed_leetcode_course
##    EDUHARNESS_DATABASE_URL=... python -m eduharness.scripts.seed_leetcode_course
from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import func, select

from eduharness.application.auth import hash_password
from eduharness.application.leetcode_service import LeetCodeService
from eduharness.infrastructure.database import Database
from eduharness.infrastructure.models import (
    AttemptKnowledgePoint,
    KnowledgeChunk,
    KnowledgeDocument,
    KnowledgePoint,
    LearningAttempt,
    Question,
    QuestionKnowledgePoint,
)
from eduharness.infrastructure.repositories import EduRepository
from eduharness.settings import get_settings

UTC = timezone.utc
SUBJECT = "leetcode"

DEMO_TEACHER_USERNAME = "demo"
DEMO_COURSE_NAME = "LeetCode Hot100 训练营"

##--------------------------------------------------------------------------
## 章节 + 题目内容定义
##--------------------------------------------------------------------------
## chapter: {code, name, description, prerequisites, doc_chunks[], questions: [...]}
## question: {editorial, title, stem(自写), difficulty, tags(额外算法标签code), approach, code}
CHAPTERS: list[dict[str, Any]] = [
    {
        "code": "lec01.array",
        "name": "数组基础",
        "description": "遍历、原地操作、前缀/差分思想。",
        "prerequisites": [],
        "doc_chunks": [
            "数组是连续内存上的元素集合，题目常考遍历、双循环穷举与空间换时间(哈希/前缀和)。",
            "套路：先暴力(时间O(n^2))再优化到O(n)或O(nlogn)；涉及连续子数组优先想前缀和。",
        ],
        "questions": [
            {
                "editorial": 1, "title": "两数之和", "difficulty": 0.3,
                "stem": "给定一个整数数组 nums 和一个整数 target，返回和为 target 的两个元素的下标。假定恰好存在一组解，且同一元素不可用两次。",
                "tags": ["lec03.hash"],
                "approach": "哈希表边遍历边查补数 target-nums[i]，命中即返回，O(n)。",
                "code": "def two_sum(nums, target):\n    seen = {}\n    for i, v in enumerate(nums):\n        if target - v in seen:\n            return [seen[target - v], i]\n        seen[v] = i\n    return []",
            },
            {
                "editorial": 283, "title": "移动零", "difficulty": 0.3,
                "stem": "把数组中的所有 0 移到末尾，同时保持非零元素的相对顺序；要求原地完成。",
                "tags": ["lec02.twopointer"],
                "approach": "快慢指针：快指针扫描，遇到非零就与慢指针位置交换，慢指针前进。",
                "code": "def move_zeroes(nums):\n    j = 0\n    for i in range(len(nums)):\n        if nums[i] != 0:\n            nums[i], nums[j] = nums[j], nums[i]\n            j += 1",
            },
            {
                "editorial": 118, "title": "杨辉三角", "difficulty": 0.3,
                "stem": "给定行数 numRows，返回杨辉三角的前 numRows 行。每行首尾为 1，其余为上一行相邻两数之和。",
                "tags": [],
                "approach": "逐行构造，行首尾填 1，中间 row[j]=prev[j-1]+prev[j]。",
                "code": "def generate(num_rows):\n    tri = []\n    for i in range(num_rows):\n        row = [1] * (i + 1)\n        for j in range(1, i):\n            row[j] = tri[i-1][j-1] + tri[i-1][j]\n        tri.append(row)\n    return tri",
            },
        ],
    },
    {
        "code": "lec02.twopointer",
        "name": "双指针 / 滑动窗口",
        "description": "相向双指针与同向滑动窗口。",
        "prerequisites": ["lec01.array"],
        "doc_chunks": [
            "双指针分相向(有序数组找配对)与同向/滑动窗口(子串/子数组计数)，能把 O(n^2) 压到 O(n)。",
            "滑动窗口模板：右指针扩张加入元素，条件不满足时左指针收缩，窗口保持单调移动。",
        ],
        "questions": [
            {
                "editorial": 11, "title": "盛最多水的容器", "difficulty": 0.55,
                "stem": "给定 n 个非负整数表示高度，选择两条竖线使其与 x 轴围成的容器装水最多。",
                "tags": ["lec01.array"],
                "approach": "相向双指针：面积=高(矮边)*宽；总是移动较矮的一边，因为矮边决定上限。",
                "code": "def max_area(height):\n    i, j, best = 0, len(height) - 1, 0\n    while i < j:\n        best = max(best, min(height[i], height[j]) * (j - i))\n        if height[i] < height[j]:\n            i += 1\n        else:\n            j -= 1\n    return best",
            },
            {
                "editorial": 15, "title": "三数之和", "difficulty": 0.6,
                "stem": "在整数数组 nums 中找出所有和为 0 且不重复的三元组。",
                "tags": ["lec03.hash"],
                "approach": "排序后固定一个数，内层用相向双指针找两数，跳过重复值去重。",
                "code": "def three_sum(nums):\n    nums.sort(); res = []\n    n = len(nums)\n    for i in range(n - 2):\n        if i > 0 and nums[i] == nums[i-1]:\n            continue\n        l, r = i + 1, n - 1\n        while l < r:\n            s = nums[i] + nums[l] + nums[r]\n            if s == 0:\n                res.append([nums[i], nums[l], nums[r]])\n                while l < r and nums[l] == nums[l+1]: l += 1\n                while l < r and nums[r] == nums[r-1]: r -= 1\n                l += 1; r -= 1\n            elif s < 0:\n                l += 1\n            else:\n                r -= 1\n    return res",
            },
            {
                "editorial": 42, "title": "接雨水", "difficulty": 0.85,
                "stem": "给定 n 个非负整数表示每个宽度为 1 的柱子的高度图，计算雨后能接多少雨水。",
                "tags": ["lec06.stack", "lec01.array"],
                "approach": "单调递减栈：遇到比栈顶高的柱子时弹栈，用两侧高度差累计水量，O(n)。",
                "code": "def trap(height):\n    stack, water = [], 0\n    for i, h in enumerate(height):\n        while stack and h > height[stack[-1]]:\n            top = stack.pop()\n            if not stack:\n                break\n            water += (min(h, height[stack[-1]]) - height[top]) * (i - stack[-1] - 1)\n        stack.append(i)\n    return water",
            },
        ],
    },
    {
        "code": "lec03.hash",
        "name": "哈希表",
        "description": "空间换时间：判重、分组、计数。",
        "prerequisites": ["lec01.array"],
        "doc_chunks": [
            "哈希表提供平均 O(1) 的插入与查找，用于把 O(n^2) 的成对比较降到 O(n)。",
            "需要'对出现过的内容做记忆'时优先考虑：字典按特征分组、集合去重。",
        ],
        "questions": [
            {
                "editorial": 49, "title": "字母异位词分组", "difficulty": 0.5,
                "stem": "给你字符串数组，把字母异位词分到同一组返回。异位词指相同字符不同排列。",
                "tags": [],
                "approach": "以排序后的字符串或字符计数元组为键，字典分组。",
                "code": "from collections import defaultdict\ndef group_anagrams(strs):\n    groups = defaultdict(list)\n    for s in strs:\n        groups[''.join(sorted(s))].append(s)\n    return list(groups.values())",
            },
            {
                "editorial": 128, "title": "最长连续序列", "difficulty": 0.6,
                "stem": "给定未排序数组，返回最长连续元素序列的长度，要求 O(n)。",
                "tags": ["lec01.array"],
                "approach": "放入集合后只从'连续段起点'(num-1 不在集合)开始向后扩展计数。",
                "code": "def longest_consecutive(nums):\n    s = set(nums); best = 0\n    for x in s:\n        if x - 1 not in s:\n            cur, y = 1, x\n            while y + 1 in s:\n                y += 1; cur += 1\n            best = max(best, cur)\n    return best",
            },
            {
                "editorial": 560, "title": "和为 K 的子数组", "difficulty": 0.7,
                "stem": "统计和为 k 的连续子数组的个数。",
                "tags": ["lec01.array", "lec13.dp"],
                "approach": "前缀和 + 哈希计数：子数组和 = 前缀差，统计差为 k 的前缀出现次数。",
                "code": "def subarray_sum(nums, k):\n    count = {0: 1}; prefix = total = 0\n    for x in nums:\n        total += x\n        prefix += count.get(total - k, 0)\n        count[total] = count.get(total, 0) + 1\n    return prefix",
            },
        ],
    },
    {
        "code": "lec04.matrix",
        "name": "矩阵 / 二维遍历",
        "description": "原地旋转、标记与有序二维查找。",
        "prerequisites": ["lec02.twopointer"],
        "doc_chunks": [
            "矩阵题常可拆成多次一维操作（旋转=转置+翻转），或用标记数组避免覆盖源值。",
            "有序二维矩阵可利用'每行每列递增'特性从右上/左下出发单调查找。",
        ],
        "questions": [
            {
                "editorial": 48, "title": "旋转图像", "difficulty": 0.6,
                "stem": "给定 n×n 矩阵，原地顺时针旋转 90 度。",
                "tags": [],
                "approach": "先按主对角线转置，再左右镜像翻转每一行。",
                "code": "def rotate(matrix):\n    n = len(matrix)\n    for i in range(n):\n        for j in range(i + 1, n):\n            matrix[i][j], matrix[j][i] = matrix[j][i], matrix[i][j]\n    for row in matrix:\n        row.reverse()",
            },
            {
                "editorial": 73, "title": "矩阵置零", "difficulty": 0.55,
                "stem": "若矩阵元素为 0，则将其所在行与列全部置 0；要求使用常数额外空间。",
                "tags": [],
                "approach": "用首行/首列做标记；先记下首行列是否有 0，再按标记置零。",
                "code": "def set_zeroes(matrix):\n    m, n = len(matrix), len(matrix[0])\n    first_row = any(matrix[0][j] == 0 for j in range(n))\n    first_col = any(matrix[i][0] == 0 for i in range(m))\n    for i in range(1, m):\n        for j in range(1, n):\n            if matrix[i][j] == 0:\n                matrix[i][0] = matrix[0][j] = 0\n    for i in range(1, m):\n        for j in range(1, n):\n            if matrix[i][0] == 0 or matrix[0][j] == 0:\n                matrix[i][j] = 0\n    if first_row:\n        for j in range(n): matrix[0][j] = 0\n    if first_col:\n        for i in range(m): matrix[i][0] = 0",
            },
            {
                "editorial": 240, "title": "搜索二维矩阵 II", "difficulty": 0.6,
                "stem": "矩阵每行从左到右递增、每列从上到下递增，判断目标值是否存在。",
                "tags": ["lec10.binarysearch"],
                "approach": "从右上角出发：小于目标则下移，大于目标则左移，O(m+n)。",
                "code": "def search_matrix(matrix, target):\n    m, n = len(matrix), len(matrix[0])\n    i, j = 0, n - 1\n    while i < m and j >= 0:\n        if matrix[i][j] == target:\n            return True\n        if matrix[i][j] < target:\n            i += 1\n        else:\n            j -= 1\n    return False",
            },
        ],
    },
    {
        "code": "lec05.linkedlist",
        "name": "链表",
        "description": "反转、合并、成环检测、快慢指针。",
        "prerequisites": [],
        "doc_chunks": [
            "链表题核心是'改指针'：画图定位 prev/cur/next，避免丢节点。",
            "成环/找中点/倒数第 k 常用快慢指针；归并/合并用哑节点简化头处理。",
        ],
        "questions": [
            {
                "editorial": 206, "title": "反转链表", "difficulty": 0.3,
                "stem": "反转单链表并返回新头。",
                "tags": [],
                "approach": "迭代三指针 prev/cur/next 原地反转；也可递归。",
                "code": "def reverse_list(head):\n    prev = None; cur = head\n    while cur:\n        nxt = cur.next\n        cur.next = prev\n        prev, cur = cur, nxt\n    return prev",
            },
            {
                "editorial": 21, "title": "合并两个有序链表", "difficulty": 0.35,
                "stem": "合并两个升序链表为一条升序链表。",
                "tags": [],
                "approach": "哑节点 + 双指针归并，谁小接谁。",
                "code": "def merge_two_lists(l1, l2):\n    dummy = tail = ListNode()\n    while l1 and l2:\n        if l1.val < l2.val:\n            tail.next, l1 = l1, l1.next\n        else:\n            tail.next, l2 = l2, l2.next\n        tail = tail.next\n    tail.next = l1 or l2\n    return dummy.next",
            },
            {
                "editorial": 141, "title": "环形链表", "difficulty": 0.3,
                "stem": "判断链表中是否存在环。",
                "tags": [],
                "approach": "快慢指针：快指针每次两步、慢指针一步，相遇即有环。",
                "code": "def has_cycle(head):\n    slow = fast = head\n    while fast and fast.next:\n        slow = slow.next\n        fast = fast.next.next\n        if slow is fast:\n            return True\n    return False",
            },
        ],
    },
    {
        "code": "lec06.stack",
        "name": "栈 / 单调栈",
        "description": "括号配对、单调栈求左右边界。",
        "prerequisites": ["lec01.array"],
        "doc_chunks": [
            "配对类用栈：入栈左括号，遇右括号弹出匹配；'最近相关'结构天然适合栈。",
            "单调栈维护单调性，能在 O(n) 内找每个元素左边/右边第一个更大(更小)的位置。",
        ],
        "questions": [
            {
                "editorial": 20, "title": "有效的括号", "difficulty": 0.3,
                "stem": "判断由 ()[]{} 组成的字符串是否配对正确且顺序合法。",
                "tags": [],
                "approach": "栈匹配：遇左括号入栈对应右括号，遇右括号必须与栈顶相等。",
                "code": "def is_valid(s):\n    stack = []\n    pairs = {')': '(', ']': '[', '}': '{'}\n    for ch in s:\n        if ch in '([{':\n            stack.append(ch)\n        elif not stack or stack.pop() != pairs[ch]:\n            return False\n    return not stack",
            },
            {
                "editorial": 155, "title": "最小栈", "difficulty": 0.45,
                "stem": "设计栈，支持 push/pop/top 并在常数时间取最小值。",
                "tags": [],
                "approach": "辅助栈同步压入当前最小值即可 O(1)。",
                "code": "class MinStack:\n    def __init__(self):\n        self.a, self.m = [], []\n    def push(self, x):\n        self.a.append(x)\n        self.m.append(x if not self.m else min(x, self.m[-1]))\n    def pop(self):\n        self.a.pop(); self.m.pop()\n    def top(self):\n        return self.a[-1]\n    def get_min(self):\n        return self.m[-1]",
            },
            {
                "editorial": 84, "title": "柱状图中最大的矩形", "difficulty": 0.85,
                "stem": "给定非负整数高度数组，找出直方图中最大的矩形面积。",
                "tags": ["lec01.array"],
                "approach": "单调递增栈维护高度边界：出栈时以当前柱为高、左右边界由栈算出宽。",
                "code": "def largest_rectangle_area(heights):\n    heights.append(0); stack = [-1]; best = 0\n    for i, h in enumerate(heights):\n        while heights[stack[-1]] > h:\n            height = heights[stack.pop()]\n            best = max(best, height * (i - stack[-1] - 1))\n        stack.append(i)\n    return best",
            },
        ],
    },
    {
        "code": "lec07.btree",
        "name": "二叉树·遍历",
        "description": "前/中/后序、深度、最近公共祖先。",
        "prerequisites": ["lec01.array", "lec06.stack"],
        "doc_chunks": [
            "树的题多用递归：先想清楚'单节点要做什么、左右子树返回什么'。",
            "递归三要素：终止条件、本层逻辑、返回值；中序在左与右之间处理当前节点。",
        ],
        "questions": [
            {
                "editorial": 94, "title": "二叉树的中序遍历", "difficulty": 0.4,
                "stem": "给定二叉树，返回中序遍历结果。",
                "tags": [],
                "approach": "递归：左-根-右；或显式栈迭代。",
                "code": "def inorder(root, out=[]):\n    out = []\n    def walk(node):\n        if node:\n            walk(node.left); out.append(node.val); walk(node.right)\n    walk(root); return out",
            },
            {
                "editorial": 104, "title": "二叉树的最大深度", "difficulty": 0.3,
                "stem": "返回二叉树的最大深度(根到最远叶子的节点数)。",
                "tags": [],
                "approach": "DFS 后序：depth = 1 + max(左,右)，空节点为 0。",
                "code": "def max_depth(root):\n    return 0 if not root else 1 + max(max_depth(root.left), max_depth(root.right))",
            },
            {
                "editorial": 236, "title": "二叉树的最近公共祖先", "difficulty": 0.75,
                "stem": "给定二叉树与两个节点 p、q，返回它们的最近公共祖先。",
                "tags": [],
                "approach": "后序自底向上：某节点左右子树分别找到 p、q 即返回该节点。",
                "code": "def lowest_common_ancestor(root, p, q):\n    if not root or root is p or root is q:\n        return root\n    l = lowest_common_ancestor(root.left, p, q)\n    r = lowest_common_ancestor(root.right, p, q)\n    return root if l and r else (l or r)",
            },
        ],
    },
    {
        "code": "lec08.treebfs",
        "name": "树的层序/DFS",
        "description": "BFS 层序、翻转、直径、树的路径类。",
        "prerequisites": ["lec07.btree"],
        "doc_chunks": [
            "按层处理用队列 BFS，每轮处理一整层即可得到层序分组。",
            "求'经过某节点的最长路径'这类题：在递归返回单侧最大深度的同时累计跨左右的总量。",
        ],
        "questions": [
            {
                "editorial": 102, "title": "二叉树的层序遍历", "difficulty": 0.5,
                "stem": "返回二叉树按层从左到右的遍历结果(每层一个数组)。",
                "tags": [],
                "approach": "队列 BFS：记录每层节点数，逐层出队收集。",
                "code": "from collections import deque\ndef level_order(root):\n    if not root: return []\n    q = deque([root]); res = []\n    while q:\n        level = []\n        for _ in range(len(q)):\n            node = q.popleft(); level.append(node.val)\n            if node.left: q.append(node.left)\n            if node.right: q.append(node.right)\n        res.append(level)\n    return res",
            },
            {
                "editorial": 226, "title": "翻转二叉树", "difficulty": 0.3,
                "stem": "翻转二叉树(左右子树镜像交换)。",
                "tags": [],
                "approach": "递归交换左右子树后翻转。",
                "code": "def invert_tree(root):\n    if root:\n        root.left, root.right = invert_tree(root.right), invert_tree(root.left)\n    return root",
            },
            {
                "editorial": 543, "title": "二叉树的直径", "difficulty": 0.6,
                "stem": "求二叉树任意两节点间路径长度的最大值(边数)。",
                "tags": [],
                "approach": "后序返回单侧最大深度，同时用左深+右深更新全局答案。",
                "code": "def diameter_of_binary_tree(root):\n    best = 0\n    def depth(node):\n        nonlocal best\n        if not node: return 0\n        l, r = depth(node.left), depth(node.right)\n        best = max(best, l + r)\n        return 1 + max(l, r)\n    depth(root); return best",
            },
        ],
    },
    {
        "code": "lec09.heap",
        "name": "堆 / TopK",
        "description": "优先队列取极值、频率 TopK、流式中位数。",
        "prerequisites": ["lec01.array"],
        "doc_chunks": [
            "找 TopK/第 K 大：维护大小固定的最小堆，堆内即答案，O(n log k)。",
            "数据流中位数：小根堆存较大一半、大根堆存较小一半(取负入堆)，平衡两边。",
        ],
        "questions": [
            {
                "editorial": 215, "title": "数组中的第 K 个最大元素", "difficulty": 0.6,
                "stem": "在未排序数组中返回第 k 个最大的元素。",
                "tags": ["lec10.binarysearch"],
                "approach": "维护大小为 k 的最小堆，堆顶即第 k 大；也可快速选择。",
                "code": "import heapq\ndef find_kth_largest(nums, k):\n    return heapq.nlargest(k, nums)[-1]",
            },
            {
                "editorial": 347, "title": "前 K 个高频元素", "difficulty": 0.6,
                "stem": "返回数组中出现频率最高的前 k 个元素。",
                "tags": ["lec03.hash"],
                "approach": "哈希计数后用大小为 k 的最小堆按频率挑 TopK。",
                "code": "import heapq, collections\ndef top_k_frequent(nums, k):\n    cnt = collections.Counter(nums)\n    return [x for x, _ in heapq.nlargest(k, cnt.items(), key=lambda t: t[1])]",
            },
            {
                "editorial": 295, "title": "数据流的中位数", "difficulty": 0.75,
                "stem": "设计类支持 addNum 与 findMedian，查询流中所有数的中位数。",
                "tags": [],
                "approach": "两个堆：大的一半用小根堆、小的一半用取负入大根堆，控制尺寸差≤1。",
                "code": "import heapq\nclass MedianFinder:\n    def __init__(self):\n        self.small, self.large = [], []  # small存负(大根堆语义)\n    def addNum(self, num):\n        heapq.heappush(self.small, -num)\n        heapq.heappush(self.large, -heapq.heappop(self.small))\n        if len(self.large) > len(self.small):\n            heapq.heappush(self.small, -heapq.heappop(self.large))\n    def findMedian(self):\n        if len(self.small) == len(self.large):\n            return (-self.small[0] + self.large[0]) / 2\n        return -self.small[0]",
            },
        ],
    },
    {
        "code": "lec10.binarysearch",
        "name": "二分查找",
        "description": "有序/旋转有序、边界、模板与复杂度。",
        "prerequisites": ["lec01.array"],
        "doc_chunks": [
            "二分适用于'单调、可判答案偏左偏右'的问题；注意开闭区间与循环不变量。",
            "旋转数组、值域二分(猜答案)都是经典变体；复杂度 O(log n)。",
        ],
        "questions": [
            {
                "editorial": 33, "title": "搜索旋转排序数组", "difficulty": 0.7,
                "stem": "升序数组在某点旋转后，搜索目标值下标(不存在返回 -1)。",
                "tags": [],
                "approach": "二分；判断 mid 落在哪段有序区再决定搜索区间。",
                "code": "def search(nums, target):\n    l, r = 0, len(nums) - 1\n    while l <= r:\n        m = (l + r) // 2\n        if nums[m] == target: return m\n        if nums[l] <= nums[m]:\n            if nums[l] <= target < nums[m]: r = m - 1\n            else: l = m + 1\n        else:\n            if nums[m] < target <= nums[r]: l = m + 1\n            else: r = m - 1\n    return -1",
            },
            {
                "editorial": 35, "title": "搜索插入位置", "difficulty": 0.4,
                "stem": "升序数组中找目标值；不存在则返回它应按序插入的位置下标。",
                "tags": [],
                "approach": "二分求第一个 >= target 的下标。",
                "code": "def search_insert(nums, target):\n    l, r = 0, len(nums)\n    while l < r:\n        m = (l + r) // 2\n        if nums[m] < target: l = m + 1\n        else: r = m\n    return l",
            },
            {
                "editorial": 153, "title": "寻找旋转排序数组中的最小值", "difficulty": 0.6,
                "stem": "升序数组在某点旋转，求最小值。",
                "tags": [],
                "approach": "二分与右端点比较判断最小值在左/右半。",
                "code": "def find_min(nums):\n    l, r = 0, len(nums) - 1\n    while l < r:\n        m = (l + r) // 2\n        if nums[m] > nums[r]: l = m + 1\n        else: r = m\n    return nums[l]",
            },
        ],
    },
    {
        "code": "lec11.backtrack",
        "name": "回溯",
        "description": "排列/组合/子集、去重、棋盘类。",
        "prerequisites": ["lec06.stack"],
        "doc_chunks": [
            "回溯=递归探索+撤销选择，穷举所有可能；模板含 选择-递归-撤销 三步。",
            "去重：同一层跳过重复值；组合(顺序无关)用 start 下标约束起点。",
        ],
        "questions": [
            {
                "editorial": 46, "title": "全排列", "difficulty": 0.5,
                "stem": "给定不含重复数字的数组，返回所有可能的全排列。",
                "tags": [],
                "approach": "用 used 数组标记已选，每层选一个未用过的数，回退撤销。",
                "code": "def permute(nums):\n    res, used = [], [False]*len(nums)\n    def dfs(path):\n        if len(path) == len(nums):\n            res.append(path[:]); return\n        for i, x in enumerate(nums):\n            if not used[i]:\n                used[i] = True; path.append(x); dfs(path)\n                path.pop(); used[i] = False\n    dfs([]); return res",
            },
            {
                "editorial": 78, "title": "子集", "difficulty": 0.5,
                "stem": "返回数组(元素互不相同)的所有子集。",
                "tags": [],
                "approach": "回溯：从 start 出发向后选，保证子集不重不漏；或按位掩码。",
                "code": "def subsets(nums):\n    res = []\n    def dfs(start, path):\n        res.append(path[:])\n        for i in range(start, len(nums)):\n            path.append(nums[i]); dfs(i+1, path); path.pop()\n    dfs(0, []); return res",
            },
            {
                "editorial": 79, "title": "单词搜索", "difficulty": 0.75,
                "stem": "在 m×n 棋盘(字母矩阵)中判断能否按相邻格子走出给定单词(同一格不能用两次)。",
                "tags": ["lec04.matrix"],
                "approach": "DFS 回溯：匹配则临时标记格子，四方向延伸，失败撤销。",
                "code": "def exist(board, word):\n    m, n = len(board), len(board[0])\n    def dfs(i, j, k):\n        if k == len(word): return True\n        if not (0 <= i < m and 0 <= j < n) or board[i][j] != word[k]:\n            return False\n        board[i][j] = '#'\n        ok = any(dfs(i+di, j+dj, k+1) for di, dj in ((1,0),(-1,0),(0,1),(0,-1)))\n        board[i][j] = word[k]\n        return ok\n    return any(dfs(i, j, 0) for i in range(m) for j in range(n))",
            },
        ],
    },
    {
        "code": "lec12.greedy",
        "name": "贪心",
        "description": "局部最优、区间划分、单调遍历。",
        "prerequisites": ["lec01.array"],
        "doc_chunks": [
            "贪心是'每一步选当前最优'并证明不劣化最终解；典型如区间调度、买卖股票。",
            "跳跃类问题维护'最远可到达'，一次遍历更新边界即可判断可达性。",
        ],
        "questions": [
            {
                "editorial": 55, "title": "跳跃游戏", "difficulty": 0.55,
                "stem": "从下标 0 出发，每个元素表示可跳跃最大长度，判断能否到达最后。",
                "tags": [],
                "approach": "维护最远可达位置，遍历更新；若当前下标超过最远即不可达。",
                "code": "def can_jump(nums):\n    reach = 0\n    for i, x in enumerate(nums):\n        if i > reach: return False\n        reach = max(reach, i + x)\n    return True",
            },
            {
                "editorial": 121, "title": "买卖股票的最佳时机", "difficulty": 0.45,
                "stem": "只允许买卖一次，求最大利润(先买后卖)。",
                "tags": ["lec13.dp"],
                "approach": "一次遍历记录历史最低价，算当天卖出的利润取最大。",
                "code": "def max_profit(prices):\n    low = float('inf'); profit = 0\n    for p in prices:\n        low = min(low, p)\n        profit = max(profit, p - low)\n    return profit",
            },
            {
                "editorial": 763, "title": "划分字母区间", "difficulty": 0.6,
                "stem": "把字符串分成尽量多的片段，使每个字母只出现在一个片段中，返回每段长度。",
                "tags": ["lec02.twopointer"],
                "approach": "先记录每个字母最后出现位置；扫描时扩张片段右边界=max(当前位置右边界,字符最后出现位置)。",
                "code": "def partition_labels(s):\n    last = {c: i for i, c in enumerate(s)}\n    res = []; start = end = 0\n    for i, c in enumerate(s):\n        end = max(end, last[c])\n        if i == end:\n            res.append(end - start + 1); start = i + 1\n    return res",
            },
        ],
    },
    {
        "code": "lec13.dp",
        "name": "动态规划",
        "description": "状态定义、转移、线性/区间/最长子序列。",
        "prerequisites": ["lec01.array", "lec12.greedy"],
        "doc_chunks": [
            "DP 三问：状态是什么、怎么转移、边界/答案取哪。先想清楚 dp[i] 含义再写循环。",
            "最长公共子序列(LCS)与最长递增子序列(LIS)是两类模板，分别对应二维与一维转移。",
        ],
        "questions": [
            {
                "editorial": 70, "title": "爬楼梯", "difficulty": 0.35,
                "stem": "每次可爬 1 或 2 阶，求爬到 n 阶有多少种不同走法。",
                "tags": [],
                "approach": "dp[i]=dp[i-1]+dp[i-2]，即斐波那契；滚动变量省空间。",
                "code": "def climb_stairs(n):\n    a, b = 1, 1\n    for _ in range(n - 1):\n        a, b = b, a + b\n    return b",
            },
            {
                "editorial": 300, "title": "最长递增子序列", "difficulty": 0.7,
                "stem": "返回最长严格递增子序列的长度(不要求连续)。",
                "tags": ["lec10.binarysearch"],
                "approach": "维护 tails 数组(递增)做二分替换，长度即答案 O(n log n)。",
                "code": "import bisect\ndef length_of_lis(nums):\n    tails = []\n    for x in nums:\n        i = bisect.bisect_left(tails, x)\n        if i == len(tails): tails.append(x)\n        else: tails[i] = x\n    return len(tails)",
            },
            {
                "editorial": 1143, "title": "最长公共子序列", "difficulty": 0.75,
                "stem": "给定两个字符串，返回它们最长公共子序列的长度。",
                "tags": [],
                "approach": "dp[i][j]：text1 前 i 与 text2 前 j 的 LCS；两字符相等+1，否则取左/上最大。",
                "code": "def longest_common_subsequence(text1, text2):\n    m, n = len(text1), len(text2)\n    dp = [[0]*(n+1) for _ in range(m+1)]\n    for i in range(1, m+1):\n        for j in range(1, n+1):\n            if text1[i-1] == text2[j-1]:\n                dp[i][j] = dp[i-1][j-1] + 1\n            else:\n                dp[i][j] = max(dp[i-1][j], dp[i][j-1])\n    return dp[m][n]",
            },
        ],
    },
    {
        "code": "lec14.graph",
        "name": "图 / BFS / 拓扑",
        "description": "连通分量、感染扩散、课程依赖。",
        "prerequisites": ["lec07.btree", "lec06.stack"],
        "doc_chunks": [
            "网格图 DFS/BFS 处理连通块：越界与访问标记是核心；感染/扩散类天然 BFS 逐层。",
            "依赖关系用拓扑排序(入度队列)；判断能否完成=能否把所有节点出队。",
        ],
        "questions": [
            {
                "editorial": 200, "title": "岛屿数量", "difficulty": 0.6,
                "stem": "二维网格(1 陆地/0 水)中，统计被水隔开的陆地连通块数量。",
                "tags": ["lec04.matrix"],
                "approach": "遍历网格，遇 1 即 DFS 淹没整块并计数。",
                "code": "def num_islands(grid):\n    if not grid: return 0\n    m, n = len(grid), len(grid[0]); ans = 0\n    def dfs(i, j):\n        if not (0 <= i < m and 0 <= j < n) or grid[i][j] != '1': return\n        grid[i][j] = '0'\n        for di, dj in ((1,0),(-1,0),(0,1),(0,-1)): dfs(i+di, j+dj)\n    for i in range(m):\n        for j in range(n):\n            if grid[i][j] == '1':\n                ans += 1; dfs(i, j)\n    return ans",
            },
            {
                "editorial": 207, "title": "课程表", "difficulty": 0.7,
                "stem": "给定课程数与依赖关系 prerequisites，判断能否完成全部课程(即图中无环)。",
                "tags": [],
                "approach": "建图统计入度，BFS 拓扑：入度 0 入队，处理数量==课程数则可行。",
                "code": "from collections import deque\ndef can_finish(n, prerequisites):\n    adj = [[] for _ in range(n)]; indeg = [0]*n\n    for a, b in prerequisites:\n        adj[b].append(a); indeg[a] += 1\n    q = deque(i for i in range(n) if indeg[i] == 0); seen = 0\n    while q:\n        u = q.popleft(); seen += 1\n        for v in adj[u]:\n            indeg[v] -= 1\n            if indeg[v] == 0: q.append(v)\n    return seen == n",
            },
            {
                "editorial": 994, "title": "腐烂的橘子", "difficulty": 0.7,
                "stem": "网格中 2 为腐烂橘子、1 为新鲜，每分钟腐烂橘子向四邻传染；返回全部腐烂所需分钟数，无法传染则 -1。",
                "tags": ["lec04.matrix"],
                "approach": "多源 BFS 分层计时；统计新鲜数，逐层感染并计数。",
                "code": "from collections import deque\ndef oranges_rotting(grid):\n    m, n = len(grid), len(grid[0]); fresh = 0; q = deque(); minutes = 0\n    for i in range(m):\n        for j in range(n):\n            if grid[i][j] == 2: q.append((i, j))\n            elif grid[i][j] == 1: fresh += 1\n    while q and fresh:\n        minutes += 1\n        for _ in range(len(q)):\n            i, j = q.popleft()\n            for di, dj in ((1,0),(-1,0),(0,1),(0,-1)):\n                ni, nj = i+di, j+dj\n                if 0 <= ni < m and 0 <= nj < n and grid[ni][nj] == 1:\n                    grid[ni][nj] = 2; fresh -= 1; q.append((ni, nj))\n    return minutes if fresh == 0 else -1",
            },
        ],
    },
    {
        "code": "lec15.bit",
        "name": "位运算 / 技巧",
        "description": "异或、计数、众数。",
        "prerequisites": [],
        "doc_chunks": [
            "异或三条性质：a^a=0、a^0=a、交换结合律；找'只出现一次'直接用异或消去成对元素。",
            "位运算适合常数空间压缩信息；众数问题可用摩尔投票一次遍历。",
        ],
        "questions": [
            {
                "editorial": 136, "title": "只出现一次的数字", "difficulty": 0.4,
                "stem": "除某个元素仅出现一次外其余均出现两次，找出它(要求线性时间、常数空间)。",
                "tags": [],
                "approach": "全员异或：成对元素抵消，剩下的就是只出现一次的数。",
                "code": "def single_number(nums):\n    x = 0\n    for v in nums: x ^= v\n    return x",
            },
            {
                "editorial": 338, "title": "比特位计数", "difficulty": 0.6,
                "stem": "返回长度 n+1 的数组，ans[i] 为 i 的二进制中 1 的个数。",
                "tags": ["lec13.dp"],
                "approach": "dp[i]=dp[i>>1]+(i&1)，即去掉最低位再加最低位本身。",
                "code": "def count_bits(n):\n    dp = [0]*(n+1)\n    for i in range(1, n+1):\n        dp[i] = dp[i >> 1] + (i & 1)\n    return dp",
            },
            {
                "editorial": 169, "title": "多数元素", "difficulty": 0.4,
                "stem": "返回数组中出现次数超过 n/2 的元素。",
                "tags": [],
                "approach": "摩尔投票：候选相同票数+1，不同-1，抵消后剩下的即众数。",
                "code": "def majority_element(nums):\n    cand, cnt = None, 0\n    for x in nums:\n        if cnt == 0: cand = x\n        cnt += 1 if x == cand else -1\n    return cand",
            },
        ],
    },
]


##每个 editorial 号对应的参考代码，供生成题解文档时回填
SOLUTION_CODE: dict[int, str] = {
    item["editorial"]: item["code"]
    for chapter in CHAPTERS
    for item in chapter["questions"]
}


##--------------------------------------------------------------------------
## 灌入逻辑
##--------------------------------------------------------------------------

async def _counts(database: Database) -> tuple[int, int]:
    async with database.session_factory() as db:
        kp = int(
            (
                await db.execute(
                    select(func.count(KnowledgePoint.id)).where(
                        KnowledgePoint.subject == SUBJECT
                    )
                )
            ).scalar_one()
        )
        q = int(
            (
                await db.execute(
                    select(func.count(Question.id)).where(
                        Question.subject == SUBJECT
                    )
                )
            ).scalar_one()
        )
        return kp, q






async def _seed_content2(database: Database) -> None:
    """正式实现：先建题与章文档骨架，再按题号回填文档内容与知识点文档。"""
    async with database.session_factory() as db:
        for chapter in CHAPTERS:
            db.add(
                KnowledgePoint(
                    subject=SUBJECT,
                    code=chapter["code"],
                    name=chapter["name"],
                    description=chapter["description"],
                    prerequisites=chapter["prerequisites"],
                )
            )
        await db.flush()

        code_to_id = {
            code: kp_id
            for code, kp_id in (
                await db.execute(
                    select(KnowledgePoint.code, KnowledgePoint.id).where(
                        KnowledgePoint.subject == SUBJECT
                    )
                )
            ).all()
        }

        # 每题：题 + 章知识点文档骨架 + 题解文档 + chunk(题解) 放到最后补
        for chapter in CHAPTERS:
            for item in chapter["questions"]:
                question = Question(
                    subject=SUBJECT,
                    stem=item["stem"],
                    question_type="coding",
                    difficulty=item["difficulty"],
                    answer={
                        "reference": {
                            "editorial": item["editorial"],
                            "title": item["title"],
                            "link_slug": None,
                        },
                        "kind": "coding",
                    },
                    explanation=item["approach"],
                )
                db.add(question)
                await db.flush()

                main_kp_id = code_to_id[chapter["code"]]
                db.add(
                    QuestionKnowledgePoint(
                        question_id=question.id,
                        knowledge_point_id=main_kp_id,
                        weight=1.0,
                    )
                )
                seen = {chapter["code"]}
                for tag in item.get("tags", []):
                    if tag in seen:
                        continue
                    seen.add(tag)
                    tag_kp = code_to_id.get(tag)
                    if tag_kp:
                        db.add(
                            QuestionKnowledgePoint(
                                question_id=question.id,
                                knowledge_point_id=tag_kp,
                                weight=0.5,
                            )
                        )

                db.add(
                    KnowledgeDocument(
                        subject=SUBJECT,
                        title=f"leetcode-solution-{question.id}",
                        source_uri=(
                            f"seed://leetcode/editorial-{item['editorial']}"
                        ),
                    )
                )

        # 章节知识点文档 + chunk
        for chapter in CHAPTERS:
            doc = KnowledgeDocument(
                subject=SUBJECT,
                title=f"leetcode-chapter-{chapter['code']}",
                source_uri=f"seed://leetcode/chapter-{chapter['code']}",
            )
            db.add(doc)
            await db.flush()
            for ordinal, text in enumerate(chapter["doc_chunks"]):
                db.add(
                    KnowledgeChunk(
                        document_id=doc.id,
                        ordinal=ordinal,
                        content=text,
                        metadata_json={
                            "chapter_code": chapter["code"]
                        },
                    )
                )

        # 题目->题解 chunk：拿 qid 后回填
        qrows = (
            await db.execute(
                select(Question.id, Question.answer).where(
                    Question.subject == SUBJECT
                )
            )
        ).all()
        solution_docs = {
            title: doc_id
            for title, doc_id in (
                await db.execute(
                    select(KnowledgeDocument.title, KnowledgeDocument.id).where(
                        KnowledgeDocument.title.like("leetcode-solution-%")
                    )
                )
            ).all()
        }
        for qid, answer in qrows:
            ref = answer.get("reference", {})
            editorial = ref.get("editorial")
            title = ref.get("title", "")
            sol_code = (
                SOLUTION_CODE.get(int(editorial), "")
                if editorial is not None
                else ""
            )
            doc_id = solution_docs[f"leetcode-solution-{qid}"]
            db.add(
                KnowledgeChunk(
                    document_id=doc_id,
                    ordinal=0,
                    content=(
                        f"【{title}】参考思路：{answer.get('explanation','')}\n"
                        f"参考实现(Python)：\n{sol_code}"
                    ),
                    metadata_json={"question_id": qid},
                )
            )
        await db.commit()




async def _seed_content_final(database: Database) -> None:
    """正式实现(最终版，供 main 调用)。"""
    await _seed_content2(database)


async def _seed_demo(
    repository: EduRepository,
    database: Database,
) -> None:
    """3 名学员 + 合成作答轨迹：制造'今日有到期复习 + 当前章待刷'。"""
    teacher = await repository.get_or_create_teacher(
        username=DEMO_TEACHER_USERNAME,
        # 与 python 课程 seed 共用演示口令，任一种子先跑都能用 demo/demo1234 登录
        password_hash=hash_password("demo1234"),
        display_name="王老师",
    )
    courses = await repository.list_teacher_courses(teacher.id)
    course = next((c for c in courses if c["subject"] == SUBJECT), None)
    if course is None:
        course_obj = await repository.create_course(
            teacher_id=teacher.id,
            name=DEMO_COURSE_NAME,
            subject=SUBJECT,
            description="LeetCode Hot100 刷题训练营(演示数据)",
        )
        course_id = course_obj.id
    else:
        course_id = course["id"]

    # 学生与作答模式：AC 时间统一落在 now-3 天，让艾宾浩斯 D+1..D+3 已在今天到期
    demo_students = [
        {
            "external_id": "demo.lc01",
            "display_name": "算法学员A",
            # (章节 code, editorial) -> 3 天前 AC；today_wrong editorial 今天答错一道
            "ac": [("lec01.array", 1)],
            "wrong_today": ("lec01.array", 283),
        },
        {
            "external_id": "demo.lc02",
            "display_name": "算法学员B",
            "ac": [
                ("lec01.array", 1),
                ("lec01.array", 283),
                ("lec01.array", 118),
                ("lec02.twopointer", 11),
            ],
            "wrong_today": ("lec02.twopointer", 15),
        },
        {
            "external_id": "demo.lc03",
            "display_name": "算法学员C",
            "ac": [("lec01.array", 118)],
            "wrong_today": ("lec01.array", 1),
        },
    ]

    async with database.session_factory() as db:
        kp_by_code = {
            code: kp_id
            for code, kp_id in (
                await db.execute(
                    select(KnowledgePoint.code, KnowledgePoint.id).where(
                        KnowledgePoint.subject == SUBJECT
                    )
                )
            ).all()
        }
        q_by_editorial: dict[int, str] = {}
        for qid, answer in (
            await db.execute(
                select(Question.id, Question.answer).where(
                    Question.subject == SUBJECT
                )
            )
        ).all():
            ref = answer.get("reference", {})
            editorial = ref.get("editorial")
            if editorial is not None:
                q_by_editorial[int(editorial)] = qid

        three_days_ago = datetime.now(UTC) - timedelta(days=3)

        for profile in demo_students:
            student = await repository.get_or_create_student(
                profile["external_id"], profile["display_name"]
            )
            await repository.enroll_student(
                course_id=course_id, student_id=student.id
            )

            existing = int(
                (
                    await db.execute(
                        select(func.count()).select_from(LearningAttempt).where(
                            LearningAttempt.student_id == student.id
                        )
                    )
                ).scalar_one()
            )
            if existing:
                continue

            for chapter_code, editorial in profile["ac"]:
                qid = q_by_editorial.get(editorial)
                if not qid:
                    continue
                attempt = LearningAttempt(
                    student_id=student.id,
                    session_id=None,
                    turn_id=None,
                    question_id=qid,
                    answer={"code": "reference", "language": "python"},
                    score=1.0,
                    max_score=1.0,
                    correctness=1.0,
                    created_at=three_days_ago,
                )
                db.add(attempt)
                await db.flush()
                db.add(
                    AttemptKnowledgePoint(
                        attempt_id=attempt.id,
                        knowledge_point_id=kp_by_code[chapter_code],
                        evidence_weight=1.0,
                    )
                )

            wrong_code, wrong_editorial = profile["wrong_today"]
            wqid = q_by_editorial.get(wrong_editorial)
            if wqid:
                attempt = LearningAttempt(
                    student_id=student.id,
                    session_id=None,
                    turn_id=None,
                    question_id=wqid,
                    answer={"code": "print('try')", "language": "python"},
                    score=0.0,
                    max_score=1.0,
                    correctness=0.0,
                )
                db.add(attempt)
                await db.flush()
                db.add(
                    AttemptKnowledgePoint(
                        attempt_id=attempt.id,
                        knowledge_point_id=kp_by_code[wrong_code],
                        evidence_weight=1.0,
                    )
                )
            await db.commit()

            # 物化掌握度(MasteryState)，供驾驶舱/个人掌握度使用
            touched_kps = {
                kp_by_code[chapter_code] for chapter_code, _ in profile["ac"]
            }
            touched_kps.add(kp_by_code[profile["wrong_today"][0]])
            for kp_id in touched_kps:
                await repository.recompute_student_kp_mastery(
                    student.id, kp_id
                )

    # 为三名学员生成"今日计划"任务，让前端/接口当天就有内容
    leetcode_service = LeetCodeService(repository)
    today = datetime.now(UTC).date()
    for profile in demo_students:
        await leetcode_service.today_plan(
            profile["external_id"] and (
                await repository.get_or_create_student(
                    profile["external_id"], profile["display_name"]
                )
            ).id,
            today=today,
            new_limit=3,
            review_limit=10,
        )


async def main() -> None:
    settings = get_settings()
    database = Database(settings.database_url)
    await database.create_schema()
    repository = EduRepository(database.session_factory)

    kp_count, q_count = await _counts(database)
    if kp_count or q_count:
        print(
            f"[seed] leetcode 课程已存在，跳过内容：{kp_count} 章 / {q_count} 题"
        )
    else:
        await _seed_content_final(database)
        kp_count, q_count = await _counts(database)
        print(f"[seed] leetcode 内容灌入：{kp_count} 章 / {q_count} 题")

    await _seed_demo(repository, database)

    async with database.session_factory() as db:
        docs = int(
            (
                await db.execute(
                    select(func.count(KnowledgeDocument.id)).where(
                        KnowledgeDocument.subject == SUBJECT
                    )
                )
            ).scalar_one()
        )
        per_chapter = (
            await db.execute(
                select(
                    KnowledgePoint.code,
                    func.count(QuestionKnowledgePoint.question_id),
                )
                .select_from(KnowledgePoint)
                .join(
                    QuestionKnowledgePoint,
                    QuestionKnowledgePoint.knowledge_point_id
                    == KnowledgePoint.id,
                )
                .join(
                    Question,
                    Question.id == QuestionKnowledgePoint.question_id,
                )
                .where(
                    KnowledgePoint.subject == SUBJECT,
                    QuestionKnowledgePoint.weight == 1.0,
                )
                .group_by(KnowledgePoint.code)
            )
        ).all()
        counts = [int(c) for _, c in per_chapter]
    print(
        f"[seed] 覆盖：章节 {len(counts)} | 每章主章题数 min={min(counts) if counts else 0} "
        f"max={max(counts) if counts else 0} | 文档 {docs} 篇"
    )
    await database.dispose()


if __name__ == "__main__":
    asyncio.run(main())
