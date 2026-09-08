import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom'
import AppLayout from '../layouts/AppLayout'
import Login from '../pages/auth/Login'
import Register from '../pages/auth/Register'
import Dashboard from '../pages/dashboard/Dashboard'
import RoleManagement from '../pages/roles/RoleManagement'
import Placeholder from '../pages/Placeholder'
import AcademicRecord from '../pages/learner/AcademicRecord'
import UserManagement from '../pages/users/UserManagement'
import SystemSettings from '../pages/settings/SystemSettings'
import ContentLibrary from '../pages/content/ContentLibrary'
import LoadingScreen from '../components/common/LoadingScreen'
import CourseManagement from '../pages/courses/CourseManagement'
import CourseBuilder from '../pages/courses/CourseBuilder'
import AssessmentManagement from '../pages/assessment/AssessmentManagement'
import SubmissionManagement from '../pages/assessment/SubmissionManagement'
import GradingCenter from '../pages/assessment/GradingCenter'
import Gradebook from '../pages/assessment/Gradebook'
import EnrollmentManagement from '../pages/enrollments/EnrollmentManagement'
import LearnerManagement from '../pages/learners/LearnerManagement'
import InstructorManagement from '../pages/instructors/InstructorManagement'
import InstructorPortal from '../pages/instructors/InstructorPortal'
import InstructorCourse from '../pages/instructors/InstructorCourse'
import InstructorLearner from '../pages/instructors/InstructorLearner'
import LearnerDashboard from '../pages/learner/LearnerDashboard'
import MyCourses from '../pages/learner/MyCourses'
import LearningWorkspace from '../pages/learner/LearningWorkspace'
import AssessmentExperience from '../pages/learner/AssessmentExperience'
import ProgressCompletion from '../pages/learner/ProgressCompletion'
import ProgressOverview from '../pages/learner/ProgressOverview'
import Achievements from '../pages/learner/Achievements'
import MyGrades from '../pages/learner/MyGrades'
import Notifications from '../pages/notifications/Notifications'
import Certificates from '../pages/certificates/Certificates'
import AdminCertificates from '../pages/certificates/AdminCertificates'
import AdminNotifications from '../pages/notifications/AdminNotifications'
import Profile from '../pages/profile/Profile'
import Analytics from '../pages/reports/Analytics'
import CohortManagement from '../pages/cohorts/CohortManagement'
import CohortDetail from '../pages/cohorts/CohortDetail'
import CommunicationCenter from '../pages/communication/CommunicationCenter'
import LearnerCohorts from '../pages/cohorts/LearnerCohorts'
import LearnerCohortDetail from '../pages/cohorts/LearnerCohortDetail'
import InstructorCohorts from '../pages/cohorts/InstructorCohorts'
import InstructorCohortDetail from '../pages/cohorts/InstructorCohortDetail'
import { useAuth } from '../contexts/AuthContext'

function Protected(){
  const {user, loading}=useAuth()
  if (loading) return <LoadingScreen/>
  return user ? <AppLayout/> : <Navigate to="/login" replace/>
}

export default function AppRoutes(){return <BrowserRouter><Routes>
  <Route path="/login" element={<Login/>}/><Route path="/register" element={<Register/>}/>
  <Route element={<Protected/>}>
    <Route path="/" element={<Dashboard/>}/><Route path="/learner" element={<LearnerDashboard/>}/><Route path="/learner/progress" element={<ProgressOverview/>}/><Route path="/learner/achievements" element={<Achievements/>}/><Route path="/learner/grades" element={<MyGrades/>}/><Route path="/learner/academic-record" element={<AcademicRecord/>}/><Route path="/learner/cohorts" element={<LearnerCohorts/>}/><Route path="/learner/cohorts/:id" element={<LearnerCohortDetail/>}/><Route path="/my-courses" element={<MyCourses/>}/><Route path="/learn/:enrollmentId" element={<LearningWorkspace/>}/><Route path="/learn/:enrollmentId/assessment/:assessmentType/:itemId" element={<AssessmentExperience/>}/><Route path="/learn/:enrollmentId/progress" element={<ProgressCompletion/>}/><Route path="/roles" element={<RoleManagement/>}/>
    <Route path="/users" element={<UserManagement/>}/><Route path="/learners" element={<LearnerManagement/>}/><Route path="/instructor" element={<InstructorPortal/>}/><Route path="/instructor/cohorts" element={<InstructorCohorts/>}/><Route path="/instructor/cohorts/:id" element={<InstructorCohortDetail/>}/><Route path="/instructors" element={<InstructorManagement/>}/><Route path="/instructor/courses/:courseId" element={<InstructorCourse/>}/><Route path="/instructor/learners/:learnerId/courses/:courseId" element={<InstructorLearner/>}/><Route path="/enrollments" element={<EnrollmentManagement/>}/><Route path="/cohorts" element={<CohortManagement/>}/><Route path="/cohorts/:id" element={<CohortDetail/>}/><Route path="/courses" element={<CourseManagement/>}/><Route path="/courses/:courseId/builder" element={<CourseBuilder/>}/>
    <Route path="/activities" element={<AssessmentManagement/>}/><Route path="/submissions" element={<SubmissionManagement/>}/><Route path="/grading" element={<GradingCenter/>}/><Route path="/gradebook" element={<Gradebook/>}/>
    <Route path="/certificates" element={<Certificates/>}/><Route path="/admin/certificates" element={<AdminCertificates/>}/><Route path="/notifications" element={<Notifications/>}/><Route path="/admin/notifications" element={<AdminNotifications/>}/><Route path="/profile" element={<Profile/>}/><Route path="/settings" element={<SystemSettings/>}/><Route path="/content" element={<ContentLibrary/>}/><Route path="/analytics" element={<Analytics/>}/><Route path="/communication" element={<CommunicationCenter/>}/>
  </Route>
  <Route path="*" element={<Navigate to="/" replace/>}/>
</Routes></BrowserRouter>}
