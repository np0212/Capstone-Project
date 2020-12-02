#!/usr/bin/env python
################################################################################
# MAIN MATHQUIZZES APP
# --------------------
#  Requires:
#    - basehandler.py
#    - signup.py
#    - grade_quiz.py
#    - create_problem.py
#
#  Authors:
#    - Matthew Moskowitz
#    - Austin Napoli
#    - Jory Pettit
#    - James Sager
#    - Nate Polly
#
#  Modifed:
#    Sun Mar 19 13:31:24 EDT 2017
################################################################################




import logging, webapp2, urllib, time, datetime, json, os.path, inspect, pytz, _json
from collections import defaultdict
from basehandler import *
from signup import *
from create_problem import *
from grade_quiz import *

from sympy import *
from sympy.parsing.sympy_parser import parse_expr
from sympy.parsing.sympy_parser import standard_transformations,\
  implicit_multiplication_application


################################################################################
# Four NDB Classes
#   - DB objects used by the MathQuizzes App
################################################################################
class Author(ndb.Model):
  identity = ndb.StringProperty(indexed=False)
  email = ndb.StringProperty(indexed=False)


class Problem(ndb.Model):
  author = ndb.StructuredProperty(Author)
  quizName = ndb.StringProperty(indexed=True)
  quizKey = ndb.StringProperty(indexed=True)
  url = ndb.StringProperty(indexed=True)
  content = ndb.StringProperty(indexed=False)
  answer = ndb.StringProperty(indexed=False)
  tags = ndb.StringProperty(indexed=False)
  difficulty = ndb.StringProperty(indexed=False)
  date = ndb.DateTimeProperty(auto_now_add=True)
  number = ndb.IntegerProperty()


class Result(ndb.Model):
  student = ndb.StructuredProperty(Author)
  studentUrl = ndb.StringProperty()
  quizName = ndb.StringProperty()
  quizUrl = ndb.StringProperty()
  courseUrl = ndb.StringProperty()
  url = ndb.StringProperty()
  floatGrade = ndb.FloatProperty(indexed=False)
  stringGrade = ndb.StringProperty(indexed=False)
  date = ndb.DateTimeProperty(auto_now_add=True)
  record = ndb.JsonProperty()
  current_problem = ndb.IntegerProperty()
  current_diff = ndb.StringProperty()
  num_correct = ndb.IntegerProperty()


class Quiz(ndb.Model):
  author = ndb.StructuredProperty(Author)
  name = ndb.StringProperty(indexed=True)
  description = ndb.StringProperty(indexed=True)
  date = ndb.DateTimeProperty(auto_now_add=True)
  isReleased = ndb.BooleanProperty(default=False)
  releaseDate = ndb.DateTimeProperty()
  easy = ndb.StructuredProperty(Problem, repeated=True)
  medium = ndb.StructuredProperty(Problem, repeated=True)
  hard = ndb.StructuredProperty(Problem, repeated=True)
  required_easy = ndb.IntegerProperty(default=0)
  required_medium = ndb.IntegerProperty(default=0)
  required_hard = ndb.IntegerProperty(default=0)
  results = ndb.StructuredProperty(Result, repeated=True)
  numberCompleted = ndb.IntegerProperty(default=0)


class Course(ndb.Model):
  name = ndb.StringProperty()
  date = ndb.DateTimeProperty(auto_now_add=True)
  numberOfStudents = ndb.IntegerProperty(default=0)
  numberOfQuizzes = ndb.IntegerProperty(default=0)
  nextQuizNum = ndb.IntegerProperty(default=1)
  numberOfAssigned = ndb.IntegerProperty(default=0)
  studentUrls = ndb.JsonProperty()
  quizUrls = ndb.JsonProperty(default=[])
  selectedQuizKey = ndb.StringProperty()
  selectedReleasedKey = ndb.StringProperty()


class User(ndb.Model):
  isTeacher = ndb.BooleanProperty()
  selectedCourseKey = ndb.StringProperty()
  myCourseKeys = ndb.JsonProperty()






################################################################################
# Function: user_key
#   - Constructs a Datastore key for a User entity.
################################################################################
DEFAULT_USER = "test@email.sc.edu"
def user_key(user=DEFAULT_USER):
  return ndb.Key('User', user)




################################################################################
# Decorator Function:  user_required
#   - Must be used on all pages that require (at least) student access
#   - Directs to logout, if not an authenticated user
#   - For use on student pages
################################################################################
def user_required(handler):
  def check_login(self, *args, **kwargs):
    auth = self.auth
    if not auth.get_user_by_session():
      self.redirect(self.uri_for('login'), abort=True)
    else:
      return handler(self, *args, **kwargs)
  return check_login




################################################################################
# Decorator Function:  instructor_required
#   - Must be used on all instructor pages
#   - Directs to logout, if not an authenticated user
#   - Directs to logout, if not an authenticated instructor
################################################################################
def instructor_required(handler):
  def check_login(self, *args, **kwargs):
    auth = self.auth
    if not auth.get_user_by_session():
      self.redirect(self.uri_for('login'), abort=True)
    if not self.user.isTeacher:
      self.redirect(self.uri_for('login'), abort=True)
    else:
      return handler(self, *args, **kwargs)
  return check_login




################################################################################
# Class:  Verification
#   - Manages Email Verification
################################################################################
class VerificationHandler(BaseHandler):
  def get(self, *args, **kwargs):
    user = None
    user_id = kwargs['user_id']
    signup_token = kwargs['signup_token']
    verification_type = kwargs['type']

    user, ts = self.user_model.get_by_auth_token(int(user_id), signup_token, 'signup')

    if not user:
      logging.info('Could not find any user with id "%s" signup token "%s"',
        user_id, signup_token)
      self.abort(404)

    # store user data in the session
    self.auth.set_session(self.auth.store.user_to_dict(user), remember=True)

    if verification_type == 'v':
      # remove signup token, we don't want users to come back with an old link
      self.user_model.delete_signup_token(user.get_id(), signup_token)
      if not user.verified:
        user.verified = True
        user.put()

      self.display_message('User email address has been verified.')
      return

    elif verification_type == 'p':
      # supply user to the page
      params = { 'user': user, 'token': signup_token }
      self.render_template('public/resetpassword.html', params)
    else:
      logging.info('verification type not supported')
      self.abort(404)




################################################################################
# Class:  Login
#   - Authenticates login
################################################################################
class LoginHandler(BaseHandler):
  def get(self):
    self._serve_page()

  def post(self):
    username = self.request.get('username')
    password = self.request.get('password')
    try:
      u = self.auth.get_user_by_password(username, password, remember=True,
        save_session=True)
      self.redirect(self.uri_for('home'))
    except (InvalidAuthIdError, InvalidPasswordError) as e:
      logging.info('Login failed for user %s because of %s', username, type(e))
      self._serve_page(True)

  def _serve_page(self, failed=False):
    username = self.request.get('username')
    params = { 'username': username, 'failed': failed }
    self.render_template('public/login.html', params)




################################################################################
# Class:  Logout
#   - Redirects to login
################################################################################
class LogoutHandler(BaseHandler):
  def get(self):
    self.auth.unset_session()
    self.redirect(self.uri_for('login'))




################################################################################
# Class:  Authenticated
#   - Should redirects to the requested page
#   - Currently redirects to home
################################################################################
class AuthenticatedHandler(BaseHandler):
  @user_required
  def get(self):
    self.render_template('home.html')




################################################################################
# Class:  Main
#   - The home page
################################################################################
class MainHandler(BaseHandler, webapp2.RequestHandler):
  @user_required
  def get(self):
    if self.user.isTeacher:
      if not hasattr(self.user,'selectedCourseKey'):
        self.render_template('instructor/inMyCourses.html', {'newuser': True})
        return
      self.render_template('instructor/inHome.html')
    else:
      if not hasattr(self.user,'selectedCourseKey'):
        self.render_template('home.html')
      else:
        r=[]
        assignedUrls=[]
        assignedquizzes=[]
        s = self.user.key.urlsafe()
        allr = Result.query().filter(Result.studentUrl == s).fetch()
        courseUrl = self.user.selectedCourseKey
        course = ndb.Key(urlsafe=courseUrl).get()
        for url in course.quizUrls:
          q=ndb.Key(urlsafe=url[2]).get()
          if q.isReleased:
            assignedUrls.append(url[2])
        for result in allr:
          if result.courseUrl==courseUrl:
            r.append(result)
            for url in assignedUrls:
              if result.quizUrl==url:
                assignedUrls.remove(url)
        for url in assignedUrls:
          assignedquizzes.append(ndb.Key(urlsafe=url).get())

        vals={'grades': r, 'assignedquizzes':assignedquizzes}
        self.render_template('home.html', vals)
  def post(self):
    quiz=ndb.Key(urlsafe=self.request.get('quizurl')).get()
    reqtype=self.request.get('type')
    required=int(self.request.get('required'))
    if reqtype == "easy":
      quiz.required_easy=required
    if reqtype == "med":
      quiz.required_medium=required
    if reqtype == "hard":
      quiz.required_hard=required
    quiz.put()



################################################################################
# Class:  My Grades
#
################################################################################
class inMyGradesHandler(BaseHandler):
  @instructor_required
  def get(self):
    r=[]
#    course = ndb.Key(urlsafe=self.user.selectedCourseKey).get()
#    if course.selectedQuizKey:
#      quiz=ndb.Key(urlsafe=course.selectedQuizKey).get()
#      r=Result.query.filter(Result.quizUrl == quiz.key.urlsafe()).fetch())
    self.render_template('instructor/inMyGrades.html', {'results':r})




################################################################################
# Class:  Quiz
#   - Take / Grade Quiz
#   - also see grade_quiz.py
################################################################################
class QuizHandler(BaseHandler, webapp2.RequestHandler):
  @user_required
  def get(self):
    if self.request.get('grade') is not '':
      g = ndb.Key(urlsafe=self.request.get('grade')).get()
      self.render_template('quiz.html', {'result':g})
    elif self.user.isTeacher:
      qkey = self.request.get('k')
      self.render_template('quiz.html', {'qkey': qkey})
    else:
      problems = []
      qkey = self.request.get('k')
      quiz = ndb.Key(urlsafe=qkey).get()
      for p in reversed(quiz.hard):
        problems.append(p)
      for p in reversed(quiz.medium):
        problems.append(p)
      for p in reversed(quiz.easy):
        problems.append(p)
      self.render_template('quiz.html', {'problems':problems, 'selectedquiz':quiz, 'qkey': qkey})
  def post(self):
    grade_quiz(self, user_key, Author, Problem, Quiz, Result)




################################################################################
# Class:  inProblem
#   - Creates a Problem
#   - Can create a new Quiz
#   - Also see create_problem.py
################################################################################
class inProblemHandler(BaseHandler, webapp2.RequestHandler):
  @instructor_required
  def get(self):
    template_values={}
    if self.request.get('p') is not '':
      prob_key = ndb.Key(urlsafe=self.request.get('p'))
      problem = prob_key.get()
      template_values = {
        'problem_content': problem.content,
        'problem_answer': problem.answer,
        'problem_tags': problem.tags,
        'problem_key': prob_key,
        'problem_difficulty': problem.difficulty,
      }
    self.render_template('instructor/inProblem.html', template_values)
  def post(self):
    create_problem(self, Problem, user_key, Author, Quiz)





################################################################################
# Class inMyProblems
#   - Displays all Problems
#   - Options:  Search, Edit, and Delete
################################################################################
class inMyProblemsHandler(BaseHandler):
  @instructor_required
  def get(self):
    allproblems = Problem.query().order(-Problem.date).fetch()
    template_values = {'allproblems': allproblems}
    self.render_template('instructor/inMyProblems.html', template_values)
  def post(self):
    user=self.user
    # get the selected course and quiz
    course = ndb.Key(urlsafe=self.user.selectedCourseKey).get()
    quiz = ndb.Key(urlsafe=course.selectedQuizKey).get()

    # Get the requested problem to copy
    copyproburl = self.request.get('copyprob')
    copyprob = ndb.Key(urlsafe=copyproburl).get()

    # Make a new problem
    problem = Problem(parent=user_key(user.email_address))
    problem.author = Author( identity=user.last_name, email=user.email_address)

    # Copy the info
    problem.content = copyprob.content
    problem.tags = copyprob.tags
    problem.answer = copyprob.answer
    problem.difficulty = copyprob.difficulty
    problem.quizName = quiz.name
    problem.put()
    problem.url=problem.key.urlsafe()
    problem.put()
    if problem.difficulty == 'Easy':
      quiz.easy.append(problem)
    if problem.difficulty == 'Medium':
      quiz.medium.append(problem)
    if problem.difficulty == 'Hard':
      quiz.hard.append(problem)
    quiz.put()
    template_values = {
      'problem_content': problem.content,
      'problem_answer': problem.answer,
      'problem_tags': problem.tags,
      'problem_key': problem.key,
      'problem_difficulty': problem.difficulty,
    }

    self.render_template('instructor/inProblem.html', template_values)




################################################################################
# Class: inMyQuizzes
#   - Displays all Quizzes and Grades
#   - Options:  Delete Quiz and Open Graded Quiz
################################################################################
class inMyQuizzesHandler(BaseHandler):
  @instructor_required
  def get(self):
    user = self.user
#    quizzes = getMyQuizList(self)
#    template_values = {'quizzes': quizzes }
    self.render_template('instructor/inMyQuizzes.html')




################################################################################
# Class:  Release Quiz
#   - Assigns the quiz to students
#   - Locks the quiz from edit
################################################################################
class ReleaseQuizHandler(BaseHandler):
  @instructor_required
  def post(self):
    course = ndb.Key(urlsafe=self.user.selectedCourseKey).get()
    course.numberOfAssigned += 1
    qkey=self.request.get('k')
    q = ndb.Key(urlsafe=qkey).get()
    q.isReleased = True
    q.releaseDate = datetime.datetime.now()
    q.put()
    if qkey == course.selectedQuizKey:
      course.selectedQuizKey = ''
    if course.quizUrls:
      for u in reversed(course.quizUrls):
        q=ndb.Key(urlsafe=u[2]).get()
        if not q.isReleased:
          course.selectedQuizKey = u[2]
    course.put()
    self.redirect('/')


################################################################################
# Class:  Delete Quiz
################################################################################
class deleteQuizHandler(BaseHandler):
  @instructor_required
  def post(self):
    course=ndb.Key(urlsafe=self.user.selectedCourseKey).get()
    course.numberOfQuizzes -= 1
    k=self.request.get('k')
    quiz=ndb.Key(urlsafe=k).get()
    if quiz.isReleased:
      course.numberOfAssigned -= 1
    course.quizUrls.remove([quiz.name, quiz.description, quiz.key.urlsafe()])
    if course.selectedQuizKey == k:
      course.selectedQuizKey=''
    if course.quizUrls:
      for u in reversed(course.quizUrls):
        q=ndb.Key(urlsafe=u[2]).get()
        if not q.isReleased:
          course.selectedQuizKey = u[2]
    course.put()
    ndb.Key(urlsafe=k).delete()
    self.redirect('/')




################################################################################
# Function:  Select Quiz
#   - Called from Create Problem (below)
################################################################################
class selectQuizHandler(BaseHandler):
  @instructor_required
  def post(self):
    qkey=self.request.get('dropdownselect')
    q=ndb.Key(urlsafe=qkey).get()
    course = ndb.Key(urlsafe=self.user.selectedCourseKey).get()
    if not q.isReleased:
      course.selectedQuizKey=qkey
    else:
      course.selectedReleasedKey=qkey
    course.put()
    # remove dangleing vars from url on return
    url, sep, var = self.request.referer.partition('?')
    self.redirect(url)




################################################################################
# Function:  Create Quiz
#   - Called from Create Problem (below)
################################################################################
class createQuizHandler(BaseHandler):
  @instructor_required
  def post(self):
    course=ndb.Key(urlsafe=self.user.selectedCourseKey).get()
    quiz = Quiz(parent=user_key(self.user.email_address))
    quiz.author = Author(
      identity=self.user.last_name,
      email=self.user.email_address)
    quiz.name = 'Quiz ' + str(course.nextQuizNum)
    quiz.description = self.request.get('qdescription')
    quiz.put()
    course.numberOfQuizzes += 1
    course.nextQuizNum += 1
    if not course.quizUrls:
      course.quizUrls=[]
    course.quizUrls.append([quiz.name, quiz.description, quiz.key.urlsafe()])
    course.selectedQuizKey=quiz.key.urlsafe()
    course.put()
    self.redirect('instructor/inProblem')





################################################################################
# Class: inAddStudents
#   - Displays Student Users
#   - Options:  Add and Remove Students from Email List
################################################################################
class inAddStudentsHandler(BaseHandler):
  @instructor_required
  def get(self):

    allS = []
    users=User.query().fetch()
    for u in users:
      if not u.isTeacher:
        allS.append(u)

    myS = []
    course=ndb.Key(urlsafe=self.user.selectedCourseKey).get()
    if hasattr(course,'studentUrls') and course.studentUrls:
      for k in course.studentUrls:
        u=ndb.Key(urlsafe=k).get()
        allS.remove(u)
        myS.append(u)

    self.render_template('instructor/inAddStudents.html',{
      'allStudents': allS,
      'myStudents': myS,
      'added': self.request.get('added'),
      'removed': self.request.get('removed')
    })




################################################################################
# Class: Add One Student
#   - Works with inAddStudents to add Students
#   - Queued by clicking on a student in the All Students column
################################################################################
class AddOneStudentHandler(BaseHandler):
  @instructor_required
  def get(self):
    url=self.request.get('s')
    k=self.user.selectedCourseKey
    course=ndb.Key(urlsafe=k).get()
    if not course.studentUrls:
      course.studentUrls = []
    course.studentUrls.append(url)
    course.numberOfStudents += 1
    course.put()
    added = ndb.Key(urlsafe=url).get()
    added = added.name + " " + added.last_name

    student=ndb.Key(urlsafe=url).get()
    if not hasattr(student, 'myCourseKeys'):
      student.myCourseKeys = []
    if not hasattr(student, 'selectedCourseKey'):
      student.myCourseKeys = []
    student.selectedCourseKey=k
    student.myCourseKeys.append(k)
    student.put()

    self.redirect("instructor/inAddStudents?added=" + added)




################################################################################
# Class: Remove One Student
#   - Works with inAddStudents to add Students
#   - Queued by clicking on a student in the MY Students column
################################################################################
class RemoveOneStudentHandler(BaseHandler):
  @instructor_required
  def get(self):
    url=self.request.get('s')
    k=self.user.selectedCourseKey
    course=ndb.Key(urlsafe=self.user.selectedCourseKey).get()
    course.studentUrls.remove(url)
    course.numberOfStudents -= 1
    course.put()
    removed = ndb.Key(urlsafe=url).get()
    removed = removed.name + " " + removed.last_name

    student=ndb.Key(urlsafe=url).get()
    for key in student.myCourseKeys:
      if key == k:
        student.myCourseKeys.remove(key)

    if student.selectedCourseKey==k:
      delattr(student, "selectedCourseKey")

    if hasattr(student.myCourseKeys, 'myCourseKeys[0]'):
      student.selectedCourseKey=student.myCourseKeys[0]

    student.put()

    self.redirect("instructor/inAddStudents?removed=" + removed)




################################################################################
# Three Classes for Editing and Deleting; Used by:
#   - MyProblems:  delete and edit problem classes
#   - MyQuizzes:   delete quiz class
################################################################################

class deleteProblemHandler(BaseHandler):
  @instructor_required
  def get(self):
    course = ndb.Key(urlsafe=self.user.selectedCourseKey).get()
    quiz = ndb.Key(urlsafe=course.selectedQuizKey).get()
    url = self.request.get('p')
    problem = ndb.Key(urlsafe=url).get()
    if problem.difficulty == 'Easy':
      for p in quiz.easy:
        if p.url == url:
          quiz.easy.remove(p)
    if problem.difficulty == 'Medium':
      for p in quiz.medium:
        if p.url == url:
          quiz.medium.remove(p)
    if problem.difficulty == 'Hard':
      for p in quiz.hard:
        if p.url == url:
          quiz.hard.remove(p)
    quiz.put()
    ndb.Key(urlsafe=url).delete()
    self.redirect("instructor/inProblem")






################################################################################
# inMyCourses Handler
################################################################################
class inMyCoursesHandler(BaseHandler):
  @instructor_required
  def get(self):
    self.render_template('instructor/inMyCourses.html', {'noCourseSelect':True})

class CreateCourseHandler(BaseHandler):
  @instructor_required
  def post(self):
    name=self.request.get('course_name')
    chars=len(name)-name.count(' ')
    if not chars:
      if not hasattr(self.user,'selectedCourseKey'):
        self.render_template('instructor/inMyCourses.html', {'newuser': True})
      else:
        self.render_template('instructor/inMyCourses.html')
        return
    c=Course()
    c.name=name
    c.numberOfQuizzes = 0
    c.numberOfStudents = 0
    c.put()
    k=c.key.urlsafe()
    if not hasattr(self.user, 'myCourseKeys'):
      self.user.myCourseKeys = []
    if not hasattr(self.user, 'selectedCourseKey'):
      self.user.myCourseKeys = []
    self.user.selectedCourseKey=k
    self.user.myCourseKeys.append(k)
    self.user.put()
    self.redirect('instructor/inAddStudents')

class DeleteCourseHandler(BaseHandler):
  @instructor_required
  def post(self):
    k=self.request.get('key')
    self.user.myCourseKeys.remove(k)
    if self.user.selectedCourseKey == k:
      self.user.selectedCourseKey = ''
      for key in reversed(self.user.myCourseKeys):
        self.user.selectedCourseKey=key
    self.user.put()
    ndb.Key(urlsafe=k).delete()
    if not hasattr(self.user,'selectedCourseKey'):
      self.render_template('instructor/inMyCourses.html', {'newuser': True})
    else:
      self.redirect('instructor/inMyCourses')


class EditCourseHandler(BaseHandler):
  @instructor_required
  def post(self):
    name=self.request.get('course_name')
    course=ndb.Key(urlsafe=self.request.get('k')).get()
    course.name=name
    course.put()
    self.redirect('instructor/inMyCourses')



class SelectCourseHandler(BaseHandler):
  @user_required
  def get(self):
    self.user.selectedCourseKey = self.request.get('key')
    self.user.put()
    # remove dangleing vars from url on return
    url, sep, var = self.request.referer.partition('?')
    self.redirect(url)





class editGradeHandler(BaseHandler):
  @instructor_required
  def post(self):
    rkey=self.request.get('r')
    changenumber=self.request.get('n')
    courseUrl=self.user.selectedCourseKey
    course = ndb.Key(urlsafe=courseUrl).get()
    quiz=ndb.Key(urlsafe=course.selectedReleasedKey).get()
    result=ndb.Key(urlsafe=rkey).get()

    # remove the old quiz result
    for r in quiz.results:
      if r.url == rkey:  quiz.results.remove(r)

    # update the zipped quiz in the result
    numproblems = 0
    correct = 0
    for p, s, a, g in result.record:
      if int(numproblems+1) == int(changenumber):
        if g:
          result.record[numproblems]=(p,s,a,0)
        else:
          result.record[numproblems]=(p,s,a,1)
          correct += 1
      elif g: correct += 1
      numproblems +=1

    # update the other result variables
    result.floatGrade=100.0*correct/numproblems
    result.stringGrade =str(round(result.floatGrade,1))+"%"

    # put everything back
    result.put()
    quiz.results.append(result)
    quiz.put()

    self.render_template('quiz.html', {'result': result })



################################################################################
# Displays Help HTML
################################################################################
class helpHandler(BaseHandler):
  @user_required
  def get(self):
    self.render_template('instructor/inHelp.html', {'noCourseSelect':True})


class problemGraderHandler(BaseHandler):

  @user_required
  def post(self):
    request_str = self.request.body
    print request_str
    request_json = json.loads(request_str)

    quiz = ndb.Key(urlsafe=request_json['quizId']).get()

    self.response.headers["Content-Type"] = "application/json"

    number = request_json['problemNumber']

    is_correct = False
    their_answer = request_json['answer']

    correct_answer = ''

    medNumber = number - len(quiz.easy);
    hardNumber = (number - len(quiz.medium) - len(quiz.easy))
    diff = 'easy'

    if number < len(quiz.easy):
      correct_answer = quiz.easy[number].answer
    elif medNumber < len(quiz.medium) and medNumber >= 0:
      correct_answer = quiz.medium[medNumber].answer
      diff = quiz.medium[medNumber].difficulty
    elif hardNumber < len(quiz.hard) and hardNumber >= 0:
      correct_answer = quiz.hard[hardNumber].answer
      diff = quiz.medium[hardNumber].difficulty

    print 'correct: ', correct_answer
    try:
      transformations = (standard_transformations +
                         (implicit_multiplication_application,))
      eq1 = parse_expr(correct_answer, transformations=transformations)
      eq2 = parse_expr(their_answer, transformations=transformations)

      # TODO fix grading
      if eq1.equals(eq2):
        is_correct = True
    except:
      pass
    json_obj = {
        'correct': is_correct,
        'difficulty': diff
    }

    self.response.out.write(json.dumps(json_obj))


class accountSummaryHandler(BaseHandler):
  @user_required
  def get(self):
    user = self.user
    email = {'email': user.email_address}
    self.render_template('settings.html', email)

  def post(self):
   user = self.user
   keyHolder = user.key.get()
   currentPassCheck = self.request.get('currentPass')
   newPass = self.request.get('newPass')

   if(user.validate_password(currentPassCheck)):
     keyHolder.set_password(newPass)
     keyHolder.put()

   self.redirect("/settings")





################################################################################
# Config / Start
################################################################################
config = {
  'webapp2_extras.auth': {
    'user_model': 'models.User',
    'user_attributes': ['name'],
    # one week below
    'token_max_age':   86400 * 7 * 1,
  },
  'webapp2_extras.sessions': {
    'secret_key': 'YOUR_SECRET_KEY'
  }
}




# [START app]
app = webapp2.WSGIApplication([

#    webapp2.Route('/public/forgot', ForgotPasswordHandler, name='forgot'),
#    webapp2.Route('/authenticated', AuthenticatedHandler, name='authenticated'),

  # public:  login, signup, etc
  webapp2.Route('/', MainHandler, name='index'),
  webapp2.Route('/public/login', LoginHandler, name='login'),
  webapp2.Route('/public/signup', SignupHandler),
  webapp2.Route('/logout', LogoutHandler, name='logout'),
  webapp2.Route('/settings', accountSummaryHandler, name='settings'),
  webapp2.Route('/<type:v|p>/<user_id:\d+>-<signup_token:.+>',
    handler=VerificationHandler, name='verification'),

  # instructor pages
  webapp2.Route('/instructor/inMyGrades', inMyGradesHandler, name='inMyGrades'),
  webapp2.Route('/instructor/inProblem', inProblemHandler, name='inProblem'),
  webapp2.Route('/instructor/inMyProblems', inMyProblemsHandler, name='inMyProblems'),
  webapp2.Route('/instructor/inMyQuizzes', inMyQuizzesHandler, name='inMyQuizzes'),
  webapp2.Route('/instructor/inAddStudents', inAddStudentsHandler, name='inAddStudents'),
  webapp2.Route('/instructor/inMyCourses', inMyCoursesHandler, name='inMyCourses'),
  webapp2.Route('/instructor/inHelp', helpHandler, name='inHelp'),
  webapp2.Route('/quiz/grade', problemGraderHandler, name='inGradeJson'),

  # edit classes
  webapp2.Route('/editGrade', editGradeHandler, name='editGrade'),
  webapp2.Route('/createQuiz', createQuizHandler, name='createQuiz'),
  webapp2.Route('/selectQuiz', selectQuizHandler, name='selectQuiz'),
  webapp2.Route('/deleteProblem', deleteProblemHandler, name='deleteProblem'),
  webapp2.Route('/addOneStudent', AddOneStudentHandler, name='addOneStudent'),
  webapp2.Route('/removeOneStudent', RemoveOneStudentHandler, name='removeOneStudent'),
  webapp2.Route('/releaseQuiz', ReleaseQuizHandler, name='releaseQuiz'),
  webapp2.Route('/deleteQuiz', deleteQuizHandler, name='deleteQuiz'),
  webapp2.Route('/createCourse', CreateCourseHandler, name='createCourse'),
  webapp2.Route('/deleteCourse', DeleteCourseHandler, name='deleteCourse'),
  webapp2.Route('/editCourse', EditCourseHandler, name='editCourse'),

  #shared class
  webapp2.Route('/selectCourse', SelectCourseHandler, name='selectCourse'),

  # student pages
  webapp2.Route('/home', MainHandler, name='home'),
  webapp2.Route('/quiz', QuizHandler, name='quiz'),

], debug=True, config=config)

logging.getLogger().setLevel(logging.DEBUG)



# [END app]
